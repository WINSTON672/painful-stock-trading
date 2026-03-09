API_KEY = ""
ANTHROPIC_API_KEY = ""
SECRET_KEY = ""
BASE_URL = "https://paper-api.alpaca.markets"

# ── Portfolio tiers ─────────────────────────────────────────────
# steady: conservative trend-following, full risk allocation
# volatile: high-momentum, half risk allocation unless strong trend
STEADY_SYMBOLS   = ["SPY", "QQQ", "MSFT"]
VOLATILE_SYMBOLS = ["NVDA", "AMD"]
SYMBOLS          = STEADY_SYMBOLS + VOLATILE_SYMBOLS

# ── Risk settings ───────────────────────────────────────────────
RISK_PERCENT_STEADY   = 0.01    # 1% account risk per steady trade
RISK_PERCENT_VOLATILE = 0.005   # 0.5% account risk per volatile trade (half size)
MAX_DAILY_LOSS        = 0.02    # halt trading if down 2% on the day

# ── Regime filter ───────────────────────────────────────────────
MA200_SLOPE_PERIOD = 20         # compare MA200 today vs 20 days ago
