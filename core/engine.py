from data.market_data import fetch_data
from strategies.ma_crossover import generate_signal
from execution.paper_executor import execute_paper_trade, get_account
from core.logger import log_trade
from core.risk_manager import within_daily_loss_limit
from core.position_sizer import calculate_position_size
import config

RISK_PERCENT = 0.01       # risk 1% of account per trade
STOP_LOSS_PCT = 0.02      # stop loss 2% below entry (ATR upgrade coming)

def run():
    print(f"[ENGINE] Fetching data for {config.SYMBOL}...")
    data = fetch_data(config.SYMBOL)

    print(f"[ENGINE] Generating signal...")
    signal = generate_signal(data)
    print(f"[ENGINE] Signal: {signal}")

    # Get live account balance
    account = get_account()
    balance = float(account.equity)
    start_balance = float(account.last_equity)
    print(f"[ENGINE] Account equity: ${balance:.2f}")

    # Daily loss guard
    if not within_daily_loss_limit(start_balance, balance):
        print(f"[ENGINE] Daily loss limit hit — no trades today.")
        return

    # Current price + stop loss
    entry_price = float(data["Close"].iloc[-1])
    stop_price = entry_price * (1 - STOP_LOSS_PCT)
    print(f"[ENGINE] Entry: ${entry_price:.2f} | Stop: ${stop_price:.2f}")

    # Risk-based position size
    shares = calculate_position_size(balance, RISK_PERCENT, entry_price, stop_price)
    print(f"[ENGINE] Position size: {shares} shares (1% risk = ${balance * RISK_PERCENT:.2f})")

    execute_paper_trade(signal, config.SYMBOL, shares)
    log_trade(signal, config.SYMBOL, shares)
