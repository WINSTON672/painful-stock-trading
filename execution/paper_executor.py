def execute_paper_trade(signal, symbol, size):
    if signal == "BUY":
        print(f"[PAPER] BUY  {symbol}  ${size:.2f}")
    elif signal == "SELL":
        print(f"[PAPER] SELL {symbol}  ${size:.2f}")
    else:
        print(f"[PAPER] HOLD {symbol} — no trade")
