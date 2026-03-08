from data.market_data import fetch_data
from strategies.ma_crossover import generate_signal
from execution.paper_executor import execute_paper_trade
from core.logger import log_trade
from core.risk_manager import check_risk
import config

def run():
    print(f"[ENGINE] Fetching data for {config.SYMBOL}...")
    data = fetch_data(config.SYMBOL)

    print(f"[ENGINE] Generating signal...")
    signal = generate_signal(data)
    print(f"[ENGINE] Signal: {signal}")

    size = check_risk(10000, config.POSITION_SIZE)

    execute_paper_trade(signal, config.SYMBOL, size)
    log_trade(signal, config.SYMBOL, size)
