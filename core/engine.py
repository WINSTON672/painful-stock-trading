import datetime
from data.market_data import fetch_data
from strategies.ma_crossover import generate_signal
from execution.paper_executor import execute_paper_trade, get_account
from core.logger import log_trade, last_trade_time
from core.risk_manager import within_daily_loss_limit
from core.position_sizer import calculate_position_size
from core.atr import atr_stop
from core.regime import detect_regime
from core.news_sentiment import get_news_sentiment
import config

ATR_MULTIPLIER     = 2.0
MIN_TRADE_INTERVAL = 6    # hours

# If news confidence >= this threshold it can block a trade
NEWS_BLOCK_THRESHOLD = 0.65


def run():
    # ── Account ───────────────────────────────────────────────
    account       = get_account()
    balance       = float(account.equity)
    start_balance = float(account.last_equity)
    print(f"[ENGINE] Account equity: ${balance:.2f}")

    if not within_daily_loss_limit(start_balance, balance):
        print("[ENGINE] Daily loss limit hit — no trades today.")
        return

    # ── Cooldown ──────────────────────────────────────────────
    last = last_trade_time()
    if last:
        hours_since = (datetime.datetime.now() - last).total_seconds() / 3600
        if hours_since < MIN_TRADE_INTERVAL:
            print(f"[ENGINE] Cooldown — {MIN_TRADE_INTERVAL - hours_since:.1f}h remaining.")
            return

    # ── Loop symbols ──────────────────────────────────────────
    for symbol in config.SYMBOLS:
        is_volatile = symbol in config.VOLATILE_SYMBOLS
        tier_label  = "VOLATILE" if is_volatile else "STEADY"
        risk_pct    = config.RISK_PERCENT_VOLATILE if is_volatile else config.RISK_PERCENT_STEADY

        print(f"\n[{symbol}] ({tier_label}) {'─'*(40-len(symbol))}")
        try:
            data   = fetch_data(symbol)
            regime = detect_regime(data)
            print(f"[{symbol}] Regime: {regime}")

            if is_volatile and regime == "SIDEWAYS":
                print(f"[{symbol}] Sideways regime — skipping volatile slot")
                continue

            signal = generate_signal(data)
            print(f"[{symbol}] Signal: {signal}")

            if signal == "HOLD":
                continue

            # ── AI News Sentiment Filter ───────────────────────
            news   = get_news_sentiment(symbol)
            n_sent = news["sentiment"]
            n_conf = news["confidence"]
            n_summ = news["summary"]

            sent_emoji = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "➡"}.get(n_sent, "➡")
            print(f"[{symbol}] 🤖 News: {sent_emoji} {n_sent} ({n_conf:.0%}) — {n_summ}")

            # Block if news strongly contradicts the technical signal
            if signal == "BUY" and n_sent == "BEARISH" and n_conf >= NEWS_BLOCK_THRESHOLD:
                print(f"[{symbol}] 🚫 AI blocked BUY — bearish news overrides technical signal")
                continue

            if signal == "SELL" and n_sent == "BULLISH" and n_conf >= NEWS_BLOCK_THRESHOLD:
                print(f"[{symbol}] 🚫 AI blocked SELL — bullish news overrides technical signal")
                continue

            # Log if news confirms
            if (signal == "BUY"  and n_sent == "BULLISH") or \
               (signal == "SELL" and n_sent == "BEARISH"):
                print(f"[{symbol}] ✅ AI confirms {signal} — news aligns with signal")

            # ── Execute ───────────────────────────────────────
            entry_price     = float(data["Close"].iloc[-1])
            stop_price, atr = atr_stop(data, multiplier=ATR_MULTIPLIER)
            shares          = calculate_position_size(balance, risk_pct, entry_price, stop_price)

            print(f"[{symbol}] Entry ${entry_price:.2f} | Stop ${stop_price:.2f} | ATR {atr:.2f} | {shares} shares")

            order = execute_paper_trade(signal, symbol, shares)
            if order is not None:
                log_trade(signal, symbol, shares,
                          entry_price=entry_price, stop_price=stop_price,
                          atr=atr, strategy=f"ema_regime+news:{n_sent}")

        except Exception as e:
            print(f"[{symbol}] ERROR: {e}")

    print("\n[ENGINE] Done.")
