import datetime
import os
import csv

LOG_FILE = "logs/trades.log"
JOURNAL_FILE = "logs/trade_journal.csv"

JOURNAL_HEADERS = ["timestamp", "strategy", "signal", "symbol", "entry_price", "stop_price", "atr", "shares"]

def _ensure_journal():
    os.makedirs("logs", exist_ok=True)
    if not os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, "w", newline="") as f:
            csv.writer(f).writerow(JOURNAL_HEADERS)

def log_trade(signal, symbol, shares, entry_price=0, stop_price=0, atr=0, strategy="ma_crossover"):
    os.makedirs("logs", exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Plain text log
    with open(LOG_FILE, "a") as f:
        f.write(f"{ts}  {signal:<4}  {symbol}  {shares} shares  entry=${entry_price:.2f}  stop=${stop_price:.2f}\n")

    # CSV journal
    _ensure_journal()
    with open(JOURNAL_FILE, "a", newline="") as f:
        csv.writer(f).writerow([ts, strategy, signal, symbol, entry_price, stop_price, atr, shares])

    print(f"[LOG] {signal} {symbol} {shares} shares @ ${entry_price:.2f} (stop ${stop_price:.2f}) logged.")

def last_trade_time():
    """Returns datetime of last logged trade, or None."""
    _ensure_journal()
    rows = []
    with open(JOURNAL_FILE, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return None
    try:
        return datetime.datetime.strptime(rows[-1]["timestamp"], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None
