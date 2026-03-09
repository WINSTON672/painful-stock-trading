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
            results.append({
                "symbol":  symbol,
                "signal":  signal,
                "regime":  regime,
                "tier":    "VOLATILE" if symbol in config.VOLATILE_SYMBOLS else "STEADY",
                "blocked": symbol in config.VOLATILE_SYMBOLS and regime == "SIDEWAYS",
            })
        except Exception as e:
            results.append({"symbol": symbol, "signal": "ERR", "regime": "ERR",
                            "tier": "STEADY", "blocked": False})
    return jsonify(results)

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
