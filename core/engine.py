import datetime
from data.market_data import fetch_data
from strategies.ma_crossover import generate_signal
from execution.paper_executor import execute_paper_trade, get_account
from core.logger import log_trade, last_trade_time
from core.risk_manager import within_daily_loss_limit
from core.position_sizer import calculate_position_size
from core.atr import atr_stop
import config

RISK_PERCENT = 0.01          # 1% of account per trade
ATR_MULTIPLIER = 2.0
MIN_TRADE_INTERVAL_HRS = 6

def run():
    # ── Account checks (once, shared across all symbols) ────
    account = get_account()
    balance = float(account.equity)
    start_balance = float(account.last_equity)
    print(f"[ENGINE] Account equity: ${balance:.2f}")

    if not within_daily_loss_limit(start_balance, balance):
        print(f"[ENGINE] Daily loss limit hit — shutting down for today.")
        return

    # ── Cooldown check ───────────────────────────────────────
    last = last_trade_time()
    if last:
        hours_since = (datetime.datetime.now() - last).total_seconds() / 3600
        if hours_since < MIN_TRADE_INTERVAL_HRS:
            remaining = MIN_TRADE_INTERVAL_HRS - hours_since
            print(f"[ENGINE] Cooldown active — {remaining:.1f}h until next trade.")
            return

    # ── Loop over all symbols ────────────────────────────────
    for symbol in config.SYMBOLS:
        print(f"\n[{symbol}] ──────────────────────────")
        try:
            data = fetch_data(symbol)
            signal = generate_signal(data)
            print(f"[{symbol}] Signal: {signal}")

            if signal == "HOLD":
                continue

            entry_price = float(data["Close"].iloc[-1])
            stop_price, atr = atr_stop(data, multiplier=ATR_MULTIPLIER)
            shares = calculate_position_size(balance, RISK_PERCENT, entry_price, stop_price)

            print(f"[{symbol}] Entry: ${entry_price:.2f} | ATR: {atr} | Stop: ${stop_price:.2f} | Shares: {shares}")

            order = execute_paper_trade(signal, symbol, shares)
            if order is not None:
                log_trade(signal, symbol, shares,
                          entry_price=entry_price, stop_price=stop_price,
                          atr=atr, strategy="ma_crossover")

        except Exception as e:
            print(f"[{symbol}] ERROR: {e}")
            continue

    print("\n[ENGINE] Done.")
