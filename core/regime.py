import config

def detect_regime(data):
    """
    Returns 'TREND' or 'SIDEWAYS' based on MA200 slope over last N days.
    TREND  → MA200 is rising → green light for all signals
    SIDEWAYS → MA200 flat/falling → block volatile trades, reduce steady
    """
    close = data["Close"].astype(float)
    ma200 = close.rolling(200).mean()

    if ma200.iloc[-1] is None or len(ma200.dropna()) < config.MA200_SLOPE_PERIOD + 1:
        return "TREND"  # not enough data, default to allowing trades

    now   = ma200.iloc[-1]
    past  = ma200.iloc[-(config.MA200_SLOPE_PERIOD + 1)]
    slope = now - past

    return "TREND" if slope > 0 else "SIDEWAYS"
