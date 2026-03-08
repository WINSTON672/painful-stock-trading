import pandas as pd
import yfinance as yf
import os

HISTORY_FOLDER = "data/history"

def load_local_data(symbol):
    path = f"{HISTORY_FOLDER}/{symbol}.csv"
    if not os.path.exists(path):
        raise FileNotFoundError(f"No local data for {symbol}. Run: python data/download_data.py")
    data = pd.read_csv(path, index_col=0, parse_dates=True, header=0, skiprows=[1, 2])
    return data

def fetch_data(symbol):
    path = f"{HISTORY_FOLDER}/{symbol}.csv"
    if os.path.exists(path):
        print(f"[DATA] Loading {symbol} from local cache...")
        return load_local_data(symbol)
    print(f"[DATA] No local cache found for {symbol}, fetching live...")
    data = yf.download(symbol, period="3mo", interval="1h", auto_adjust=True, progress=False)
    return data
