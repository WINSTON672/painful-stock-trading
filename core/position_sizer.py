def calculate_position_size(account_balance, risk_percent, entry_price, stop_price):
    risk_amount = account_balance * risk_percent
    risk_per_share = abs(entry_price - stop_price)

    if risk_per_share == 0:
        return 0

    shares = risk_amount / risk_per_share
    return int(shares)
