import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
import time
import queue
import threading
import contextlib
import io
from collections import deque
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, jsonify, Response, request

import config
from execution.paper_executor import get_account, client as alpaca_client
from data.market_data import load_local_data
from strategies.ma_crossover import generate_signal
from core.regime import detect_regime
from core.logger import JOURNAL_FILE
from core.news_sentiment import get_news_sentiment

# Alpaca market data client (for intraday bars)
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

_data_client = StockHistoricalDataClient(config.API_KEY, config.SECRET_KEY)

app = Flask(__name__)

# ── Live log buffer ───────────────────────────────────────────────
# Stores last 200 lines; SSE clients get new lines as they arrive
LOG_BUFFER   = deque(maxlen=200)
LOG_QUEUE    = queue.Queue()   # new lines pushed here → SSE subscribers pick up
BOT_RUNNING  = threading.Event()
RUN_NOW      = threading.Event()  # set to trigger immediate run

BOT_INTERVAL = 5 * 60  # run engine every 5 minutes

def _emit(line):
    """Add a line to the log buffer and notify SSE subscribers."""
    ts   = time.strftime("%H:%M:%S")
    msg  = f"[{ts}] {line}"
    LOG_BUFFER.append(msg)
    LOG_QUEUE.put(msg)

# ── Bot loop (background thread) ──────────────────────────────────
def _bot_loop():
    import core.engine as engine_mod

    _emit("🤖 Bot loop started — running every 5 minutes")
    BOT_RUNNING.set()

    while True:
        _emit("─" * 48)
        _emit("▶ Running engine…")

        # Capture all stdout from the engine
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                engine_mod.run()
        except Exception as e:
            _emit(f"❌ Engine error: {e}")

        for line in buf.getvalue().splitlines():
            if line.strip():
                _emit(line)

        _emit("✓ Engine cycle complete")

        # Wait 5 minutes OR until RUN_NOW is set
        RUN_NOW.wait(timeout=BOT_INTERVAL)
        RUN_NOW.clear()

def start_bot_loop():
    t = threading.Thread(target=_bot_loop, daemon=True)
    t.start()

# ── Helpers ───────────────────────────────────────────────────────
@contextlib.contextmanager
def _silent():
    with open(os.devnull, "w") as null:
        with contextlib.redirect_stdout(null):
            yield

# ── Routes ────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/account")
def api_account():
    try:
        acct = get_account()
        equity       = float(acct.equity)
        last_equity  = float(acct.last_equity)
        buying_power = float(acct.buying_power)
        day_pnl      = equity - last_equity
        day_pnl_pct  = (day_pnl / last_equity * 100) if last_equity else 0
        return jsonify({
            "equity":       round(equity, 2),
            "buying_power": round(buying_power, 2),
            "day_pnl":      round(day_pnl, 2),
            "day_pnl_pct":  round(day_pnl_pct, 3),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/positions")
def api_positions():
    try:
        positions = alpaca_client.get_all_positions()
        result = []
        for p in positions:
            result.append({
                "symbol":          p.symbol,
                "qty":             int(float(p.qty)),
                "entry_price":     round(float(p.avg_entry_price), 2),
                "current_price":   round(float(p.current_price), 2),
                "market_value":    round(float(p.market_value), 2),
                "unrealized_pl":   round(float(p.unrealized_pl), 2),
                "unrealized_plpc": round(float(p.unrealized_plpc) * 100, 2),
                "tier": "VOLATILE" if p.symbol in config.VOLATILE_SYMBOLS else "STEADY",
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/trades")
def api_trades():
    try:
        if not os.path.exists(JOURNAL_FILE):
            return jsonify([])
        with open(JOURNAL_FILE, "r") as f:
            rows = list(csv.DictReader(f))
        return jsonify(list(reversed(rows[-20:])))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/signals")
def api_signals():
    results = []
    for symbol in config.SYMBOLS:
        try:
            data = load_local_data(symbol)
            with _silent():
                signal = generate_signal(data)
                regime = detect_regime(data)
            news = get_news_sentiment(symbol)
            results.append({
                "symbol":           symbol,
                "signal":           signal,
                "regime":           regime,
                "tier":             "VOLATILE" if symbol in config.VOLATILE_SYMBOLS else "STEADY",
                "blocked":          symbol in config.VOLATILE_SYMBOLS and regime == "SIDEWAYS",
                "news_sentiment":   news["sentiment"],
                "news_confidence":  news["confidence"],
                "news_summary":     news["summary"],
            })
        except Exception as e:
            results.append({"symbol": symbol, "signal": "ERR", "regime": "ERR",
                            "tier": "STEADY", "blocked": False,
                            "news_sentiment": "NEUTRAL", "news_confidence": 0, "news_summary": ""})
    return jsonify(results)


@app.route("/api/news/<symbol>")
def api_news(symbol):
    """Full news headlines + sentiment for a symbol."""
    try:
        data = get_news_sentiment(symbol.upper(), force=False)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/equity")
def api_equity():
    try:
        from backtest.backtest_engine import run_backtest
        data = load_local_data("SPY")
        with _silent():
            _, _, pv = run_backtest(data, initial_cash=100_000, symbol="SPY")
        dates     = [str(d.date()) for d, _ in pv]
        values    = [round(v, 2) for _, v in pv]
        bah_start = float(data["Close"].iloc[201])
        bah_vals  = [round(100_000 * float(data["Close"].iloc[i]) / bah_start, 2)
                     for i in range(201, len(data))]
        return jsonify({"dates": dates, "strategy": values, "buy_hold": bah_vals})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/run", methods=["POST"])
def api_run():
    """Trigger an immediate engine run (skips the 5-min wait)."""
    RUN_NOW.set()
    return jsonify({"status": "triggered"})

@app.route("/api/log/history")
def api_log_history():
    """Return current log buffer for initial page load."""
    return jsonify(list(LOG_BUFFER))

@app.route("/api/log/stream")
def api_log_stream():
    """SSE endpoint — pushes new log lines to the browser in real time."""
    def generate():
        # Send existing buffer first
        for line in list(LOG_BUFFER):
            yield f"data: {line}\n\n"
        # Then stream new lines as they arrive
        while True:
            try:
                line = LOG_QUEUE.get(timeout=15)
                yield f"data: {line}\n\n"
            except queue.Empty:
                yield "data: \n\n"  # keepalive ping

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/chart/<symbol>")
def api_chart(symbol):
    period = request.args.get("period", "1Y")
    symbol = symbol.upper()

    try:
        if period in ("1Y", "3M", "1M"):
            # Use local CSV (daily bars)
            data = load_local_data(symbol)
            cutoff = {
                "1Y": datetime.now() - timedelta(days=365),
                "3M": datetime.now() - timedelta(days=90),
                "1M": datetime.now() - timedelta(days=30),
            }[period]
            data = data[data.index >= cutoff]

            candles = []
            for ts, row in data.iterrows():
                candles.append({
                    "time":   int(ts.replace(tzinfo=timezone.utc).timestamp()),
                    "open":   round(float(row["Open"]),  4),
                    "high":   round(float(row["High"]),  4),
                    "low":    round(float(row["Low"]),   4),
                    "close":  round(float(row["Close"]), 4),
                    "volume": int(float(row["Volume"])),
                })

            # EMA / MA overlays
            import pandas as pd
            import ta
            close = data["Close"].astype(float)
            ema20  = close.ewm(span=20).mean()
            ema50  = close.ewm(span=50).mean()
            ma200  = close.rolling(200).mean()
            rsi14  = ta.momentum.RSIIndicator(close, window=14).rsi()

            def to_line(series):
                return [{"time": int(ts.replace(tzinfo=timezone.utc).timestamp()),
                          "value": round(float(v), 4)}
                        for ts, v in series.items() if not (v != v)]  # skip NaN

            return jsonify({
                "candles": candles,
                "ema20":   to_line(ema20),
                "ema50":   to_line(ema50),
                "ma200":   to_line(ma200),
                "rsi":     to_line(rsi14),
            })

        else:
            # Intraday — fetch from Alpaca
            tf_map = {
                "5min": (TimeFrame(5,  TimeFrameUnit.Minute), timedelta(days=5)),
                "1min": (TimeFrame(1,  TimeFrameUnit.Minute), timedelta(days=2)),
                "1sec": (TimeFrame(1,  TimeFrameUnit.Minute), timedelta(hours=6)),
            }
            tf, lookback = tf_map.get(period, tf_map["5min"])
            start = datetime.now(timezone.utc) - lookback

            req  = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start)
            bars = _data_client.get_stock_bars(req)[symbol]

            candles = [{"time":   int(b.timestamp.replace(tzinfo=timezone.utc).timestamp()),
                        "open":   round(float(b.open),   4),
                        "high":   round(float(b.high),   4),
                        "low":    round(float(b.low),    4),
                        "close":  round(float(b.close),  4),
                        "volume": int(b.volume)} for b in bars]

            # Latest quote for real-time last price
            quote = _data_client.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
            last_price = round((float(quote.ask_price) + float(quote.bid_price)) / 2, 4)

            return jsonify({"candles": candles, "last_price": last_price})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """AI trading assistant — uses Claude if ANTHROPIC_API_KEY is set, otherwise rule-based."""
    try:
        msg = (request.json or {}).get("message", "").strip()
        if not msg:
            return jsonify({"error": "No message"}), 400

        # ── Build live context ────────────────────────────────────
        try:
            acct        = get_account()
            equity      = float(acct.equity)
            last_eq     = float(acct.last_equity)
            day_pnl     = equity - last_eq
            day_pct     = day_pnl / last_eq * 100 if last_eq else 0
        except Exception:
            equity = last_eq = day_pnl = day_pct = 0

        try:
            positions   = alpaca_client.get_all_positions()
            pos_text    = ", ".join(
                f"{p.symbol} ({p.qty} sh, ${float(p.unrealized_pl):+.0f})"
                for p in positions
            ) or "none"
        except Exception:
            pos_text    = "unavailable"

        sig_lines = []
        news_lines = []
        for symbol in config.SYMBOLS:
            try:
                data = load_local_data(symbol)
                with _silent():
                    sig = generate_signal(data)
                    reg = detect_regime(data)
                sig_lines.append(f"{symbol}:{sig}/{reg}")
            except Exception:
                pass
            try:
                n = get_news_sentiment(symbol)
                news_lines.append(f"{symbol}:{n['sentiment']}({n['confidence']:.0%}) {n['summary']}")
            except Exception:
                pass
        sig_text  = "  ".join(sig_lines)  or "unavailable"
        news_text = "\n".join(news_lines) or "unavailable"

        system_ctx = f"""You are a concise AI trading assistant for AutoTrader Pro, a paper trading bot.

Live portfolio:
• Equity: ${equity:,.2f}  Day P&L: ${day_pnl:+,.2f} ({day_pct:+.2f}%)
• Positions: {pos_text}
• Signals (symbol:signal/regime): {sig_text}

Strategy: EMA crossover (Fast>Slow + price>Trend + RSI<75 = BUY; opposite = SELL).
Tiers: STEADY (SPY,QQQ,MSFT) 1% risk; VOLATILE (NVDA,AMD) 0.5% risk, blocked if sideways.
Stops: 2×ATR below entry. Max daily loss: 2%. 6-hour cooldown between trades.

AI news filter: if news sentiment strongly contradicts the technical signal (≥65% confidence), the trade is blocked.

Current news sentiment:
{news_text}

Be concise (2-4 sentences max). Use plain language. No disclaimers."""

        # ── Try Claude API ────────────────────────────────────────
        api_key = getattr(config, "ANTHROPIC_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            try:
                import anthropic as _ant
                _c = _ant.Anthropic(api_key=api_key)
                resp = _c.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    system=system_ctx,
                    messages=[{"role": "user", "content": msg}],
                )
                return jsonify({"response": resp.content[0].text})
            except Exception:
                pass

        # ── Rule-based AI (free, no API needed) ──────────────────
        m = msg.lower()

        if any(w in m for w in ["portfolio", "doing", "today", "performance", "pnl", "p&l", "how am i"]):
            word = "up" if day_pnl >= 0 else "down"
            r = f"You're {word} ${abs(day_pnl):,.2f} ({day_pct:+.2f}%) today. Equity: ${equity:,.2f}. {f'Positions: {pos_text}.' if pos_text != 'none' else 'No open positions.'}"

        elif any(w in m for w in ["news", "headline", "sentiment"]):
            lines = []
            for sym in config.SYMBOLS:
                try:
                    n = get_news_sentiment(sym)
                    emoji = {"BULLISH":"📈","BEARISH":"📉","NEUTRAL":"➡"}.get(n["sentiment"],"➡")
                    lines.append(f"{sym}: {emoji} {n['sentiment']} — {n['summary']}")
                except Exception:
                    pass
            r = "Current news sentiment:\n" + "\n".join(lines) if lines else "Could not fetch news."

        elif any(w in m for w in ["signal", "buy", "sell", "should i trade", "should i buy", "should i sell"]):
            buys  = [s for s in sig_text.split("  ") if ":BUY"  in s]
            sells = [s for s in sig_text.split("  ") if ":SELL" in s]
            parts = []
            if buys:  parts.append(f"BUY signals: {', '.join(b.split(':')[0] for b in buys)}")
            if sells: parts.append(f"SELL signals: {', '.join(s.split(':')[0] for s in sells)}")
            if not parts: parts = ["All HOLD — no action right now"]
            r = ". ".join(parts) + ". Bot runs every 5 min, or hit Run Now."

        elif any(w in m for w in ["strategy", "how does", "explain", "work", "ema", "fast", "slow", "trend"]):
            r = ("Strategy: BUY when the Fast line (EMA20) crosses above the Slow line (EMA50) "
                 "AND price is above the Trend line (MA200) AND RSI < 75. "
                 "SELL on the reverse. Volatile stocks (NVDA, AMD) are blocked when the market is sideways. "
                 "News sentiment can also block trades if strongly against the signal.")

        elif any(w in m for w in ["risk", "stop", "loss", "drawdown", "safe"]):
            r = ("Each trade risks at most 1% (SPY/QQQ/MSFT) or 0.5% (NVDA/AMD) of your account. "
                 f"That's about ${equity * 0.01:,.0f} per steady trade right now. "
                 "Stop loss is set at 2× ATR below entry. Bot halts all trading if you're down 2% in a day.")

        elif any(w in m for w in ["position", "holding", "open", "what do i own"]):
            r = f"Open positions: {pos_text}." if pos_text != "none" else "No open positions right now."

        elif any(w in m for w in ["equity", "balance", "money", "worth", "account"]):
            bp = float(get_account().buying_power)
            r = f"Account equity: ${equity:,.2f}. Buying power: ${bp:,.2f}. Day P&L: ${day_pnl:+,.2f} ({day_pct:+.2f}%)."

        elif any(w in m for w in ["nvda", "amd", "spy", "qqq", "msft"]):
            sym = next((s for s in ["NVDA","AMD","SPY","QQQ","MSFT"] if s.lower() in m), None)
            if sym:
                sig_info = next((s for s in sig_text.split("  ") if s.startswith(sym+":")), "no data")
                try:
                    n = get_news_sentiment(sym)
                    emoji = {"BULLISH":"📈","BEARISH":"📉","NEUTRAL":"➡"}.get(n["sentiment"],"➡")
                    news_bit = f" News: {emoji} {n['sentiment']} ({n['confidence']:.0%}) — {n['summary']}"
                except Exception:
                    news_bit = ""
                r = f"{sym} — Signal: {sig_info}.{news_bit}"
            else:
                r = f"Signals: {sig_text}"

        elif any(w in m for w in ["bot", "running", "when", "next", "run"]):
            r = "The bot runs automatically every 5 minutes. Hit ⚡ Run Now in the top bar to trigger it immediately. Check the Bot Log tab to see what it's doing."

        else:
            # Generic summary
            word = "up" if day_pnl >= 0 else "down"
            buys = sig_text.count(":BUY")
            r = (f"Portfolio {word} ${abs(day_pnl):,.2f} today. Equity ${equity:,.2f}. "
                 f"{buys} BUY signal{'s' if buys!=1 else ''} active. "
                 f"Try asking: 'How are my signals?', 'What's the news?', 'Explain the strategy'")

        return jsonify({"response": r})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/quotes")
def api_quotes():
    """Last price + day change for all symbols from local CSV data."""
    result = {}
    for symbol in config.SYMBOLS:
        try:
            data = load_local_data(symbol)
            last = float(data["Close"].iloc[-1])
            prev = float(data["Close"].iloc[-2])
            chg  = last - prev
            result[symbol] = {
                "price":      round(last, 2),
                "change":     round(chg, 2),
                "change_pct": round(chg / prev * 100, 2),
            }
        except Exception:
            result[symbol] = {"price": 0, "change": 0, "change_pct": 0}
    return jsonify(result)


@app.route("/api/balance/history")
def api_balance_history():
    """Account equity history from Alpaca portfolio history API."""
    try:
        period = request.args.get("period", "1M")
        alpaca_period = {"1Y": "1A", "3M": "3M", "1M": "1M",
                         "5min": "1D", "1min": "1D", "1sec": "1D"}.get(period, "1M")

        history = alpaca_client.get_portfolio_history(period=alpaca_period, timeframe="1D")
        points = []
        for ts, val in zip(history.timestamp, history.equity):
            if val is not None and val > 0:
                points.append({
                    "time":  int(ts),
                    "value": round(float(val), 2),
                })
        return jsonify(points)
    except Exception as e:
        return jsonify({"error": str(e), "points": []}), 200


if __name__ == "__main__":
    start_bot_loop()
    print("Dashboard → http://localhost:5001")
    app.run(debug=False, host="0.0.0.0", port=5001, threaded=True)
