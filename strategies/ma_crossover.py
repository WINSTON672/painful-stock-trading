import ta

def generate_signal(data):
    data = data.copy()
    close = data["Close"].astype(float)

    # EMA reacts faster than SMA — earlier trend entry
    data["ema_fast"]  = close.ewm(span=20).mean()
    data["ema_slow"]  = close.ewm(span=50).mean()
    data["ma_trend"]  = close.rolling(200).mean()   # keep 200 SMA as long-term anchor
    data["rsi"]       = ta.momentum.RSIIndicator(close, window=14).rsi()

    ema_fast  = data["ema_fast"].iloc[-1]
    ema_slow  = data["ema_slow"].iloc[-1]
    ma_trend  = data["ma_trend"].iloc[-1]
    price     = close.iloc[-1]
    rsi       = data["rsi"].iloc[-1]

    bullish = ema_fast > ema_slow and price > ma_trend
    bearish = ema_fast < ema_slow and price < ma_trend

    print(f"  EMA20={ema_fast:.2f}  EMA50={ema_slow:.2f}  MA200={ma_trend:.2f}  RSI={rsi:.1f}")

    if bullish and rsi < 75:    # widened from 65 — capture strong momentum
        return "BUY"
    elif bearish and rsi > 25:  # widened from 35
        return "SELL"
    return "HOLD"
