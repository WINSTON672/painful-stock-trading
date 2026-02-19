import pandas as pd

file_path = "data/AAPL_5Min.csv"

df = pd.read_csv(file_path, index_col="timestamp", parse_dates=True)

lookback = 20

recent_high = df["high"].tail(lookback).max()
latest_close = df["close"].iloc[-1]

print("Latest close:", latest_close)
print("Recent high:", recent_high)

if latest_close > recent_high:
    print("BUY SIGNAL: Breakout detected")
else:
    print("No breakout signal")

