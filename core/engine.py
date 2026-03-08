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
ATR_MULTIPLIER = 2.0         # stop = entry - (ATR * 2)
MIN_TRADE_INTERVAL_HRS = 6   # cooldown between trades

def run():
    print(f"[ENGINE] Fetching data for {config.SYMBOL}...")
    data = fetch_data(config.SYMBOL)

    # ── Cooldown check ──────────────────────────────────────
    last = last_trade_time()
    if last:
        hours_since = (datetime.datetime.now() - last).total_seconds() / 3600
        if hours_since < MIN_TRADE_INTERVAL_HRS:
            remaining = MIN_TRADE_INTERVAL_HRS - hours_since
            print(f"[ENGINE] Cooldown active — {remaining:.1f}h until next trade allowed.")
            return

    # ── Signal ──────────────────────────────────────────────
    print(f"[ENGINE] Generating signal...")
    signal = generate_signal(data)
    print(f"[ENGINE] Signal: {signal}")

    if signal == "HOLD":
        print(f"[ENGINE] No action.")
        return

    # ── Account checks ──────────────────────────────────────
    account = get_account()
    balance = float(account.equity)
    start_balance = float(account.last_equity)
    print(f"[ENGINE] Account equity: ${balance:.2f}")

    if not within_daily_loss_limit(start_balance, balance):
        print(f"[ENGINE] Daily loss limit hit — no trades today.")
        return

    # ── ATR stop + position size ─────────────────────────────
    entry_price = float(data["Close"].iloc[-1])
    stop_price, atr = atr_stop(data, multiplier=ATR_MULTIPLIER)
    shares = calculate_position_size(balance, RISK_PERCENT, entry_price, stop_price)

    print(f"[ENGINE] Entry: ${entry_price:.2f} | ATR: {atr} | Stop: ${stop_price:.2f}")
    print(f"[ENGINE] Position size: {shares} shares (1% risk = ${balance * RISK_PERCENT:.2f})")

    # ── Execute + log ────────────────────────────────────────
    order = execute_paper_trade(signal, config.SYMBOL, shares)
    if order is not None:
        log_trade(signal, config.SYMBOL, shares,
                  entry_price=entry_price, stop_price=stop_price,
                  atr=atr, strategy="ma_crossover")
