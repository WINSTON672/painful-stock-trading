from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
import config

client = TradingClient(config.API_KEY, config.SECRET_KEY, paper=True)

def get_account():
    return client.get_account()

def execute_paper_trade(signal, symbol, size):
    if signal == "HOLD":
        print(f"[ALPACA] HOLD {symbol} — no order placed")
        return None

    # Calculate number of shares based on trade value
    account = get_account()
    buying_power = float(account.buying_power)
    print(f"[ALPACA] Account buying power: ${buying_power:.2f}")

    # Use notional (dollar amount) order
    side = OrderSide.BUY if signal == "BUY" else OrderSide.SELL

    # Don't sell if we have no position
    if side == OrderSide.SELL:
        try:
            position = client.get_open_position(symbol)
            if float(position.qty) <= 0:
                print(f"[ALPACA] No position in {symbol} to sell — skipping")
                return None
        except Exception:
            print(f"[ALPACA] No position in {symbol} to sell — skipping")
            return None

    order_data = MarketOrderRequest(
        symbol=symbol,
        notional=round(size, 2),
        side=side,
        time_in_force=TimeInForce.DAY,
    )

    order = client.submit_order(order_data)
    print(f"[ALPACA] {signal} order submitted: {order.id} | {symbol} | ${size:.2f}")
    return order
