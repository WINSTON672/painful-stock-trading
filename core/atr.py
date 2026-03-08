import pandas as pd

def calculate_atr(data, period=14):
    high = data["High"].astype(float)
    low = data["Low"].astype(float)
    close = data["Close"].astype(float)

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean()
    return float(atr.iloc[-1])

def atr_stop(data, multiplier=2.0, period=14):
    atr = calculate_atr(data, period)
    entry = float(data["Close"].iloc[-1])
    stop = entry - (atr * multiplier)
    return round(stop, 2), round(atr, 4)
