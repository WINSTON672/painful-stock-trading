import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yfinance as yf
import config

SYMBOLS = config.SYMBOLS
FOLDER = "data/history"

os.makedirs(FOLDER, exist_ok=True)

for symbol in SYMBOLS:
    print(f"Downloading {symbol}...")
    data = yf.download(symbol, start="2018-01-01", auto_adjust=True, progress=False)
    path = f"{FOLDER}/{symbol}.csv"
    data.to_csv(path)
    print(f"  Saved to {path} ({len(data)} rows)")

print("\nAll done.")
