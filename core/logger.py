import datetime
import os

LOG_FILE = "logs/trades.log"

def log_trade(signal, symbol, size):
    os.makedirs("logs", exist_ok=True)
    with open(LOG_FILE, "a") as f:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{ts}  {signal:<4}  {symbol}  ${size:.2f}\n")
    print(f"[LOG] {signal} {symbol} ${size:.2f} logged.")
