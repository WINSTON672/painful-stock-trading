from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
import config

client = TradingClient(config.API_KEY, config.SECRET_KEY, paper=True)

def get_account():
    return client.get_account()

def get_position(symbol):
    """Returns (holding, qty). holding=True if we own shares."""
    try:
        pos = client.get_open_position(symbol)
        qty = int(float(pos.qty))
        return qty > 0, qty
    except Exception:
        return False, 0

def execute_paper_trade(signal, symbol, shares):
    if signal == "HOLD" or shares <= 0:
        print(f"[ALPACA] HOLD {symbol} — no order placed")
        return None

    holding, held_qty = get_position(symbol)
    account = get_account()
    buying_power = float(account.buying_power)
    print(f"[ALPACA] Buying power: ${buying_power:.2f} | Holding {symbol}: {held_qty} shares")

    if signal == "BUY":
        if holding:
            print(f"[ALPACA] Already holding {symbol} — skipping duplicate BUY")
            return None
        side = OrderSide.BUY

    elif signal == "SELL":
        if not holding:
            print(f"[ALPACA] No position in {symbol} to sell — skipping")
            return None
        side = OrderSide.SELL
        shares = min(shares, held_qty)  # never sell more than we hold

    order_data = MarketOrderRequest(
        symbol=symbol,
        qty=shares,
        side=side,
        time_in_force=TimeInForce.DAY,
    )

    order = client.submit_order(order_data)
    print(f"[ALPACA] {signal} order submitted: {order.id} | {shares} shares of {symbol}")
    return order
