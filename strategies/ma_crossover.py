import ta

def generate_signal(data):
    data = data.copy()
    close = data["Close"].astype(float)

    data["ma_fast"]  = close.rolling(20).mean()
    data["ma_slow"]  = close.rolling(50).mean()
    data["ma_trend"] = close.rolling(200).mean()
    data["rsi"]      = ta.momentum.RSIIndicator(close, window=14).rsi()

    ma_fast  = data["ma_fast"].iloc[-1]
    ma_slow  = data["ma_slow"].iloc[-1]
    ma_trend = data["ma_trend"].iloc[-1]
    price    = close.iloc[-1]
    rsi      = data["rsi"].iloc[-1]

    ma_bullish = ma_fast > ma_slow
    ma_bearish = ma_fast < ma_slow
    trend_up   = price > ma_trend
    trend_down = price < ma_trend

    print(f"  MA20={ma_fast:.2f}  MA50={ma_slow:.2f}  MA200={ma_trend:.2f}  RSI={rsi:.1f}")

    if ma_bullish and trend_up and rsi < 65:
        return "BUY"
    elif ma_bearish and trend_down and rsi > 35:
        return "SELL"
    return "HOLD"
