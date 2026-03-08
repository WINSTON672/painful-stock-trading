def generate_signal(data):
    data = data.copy()
    data["ma_fast"] = data["Close"].rolling(20).mean()
    data["ma_slow"] = data["Close"].rolling(50).mean()

    if data["ma_fast"].iloc[-1] > data["ma_slow"].iloc[-1]:
        return "BUY"
    elif data["ma_fast"].iloc[-1] < data["ma_slow"].iloc[-1]:
        return "SELL"
    return "HOLD"
