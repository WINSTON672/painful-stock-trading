import config

def check_risk(account_balance, position_size=None):
    size = position_size or config.POSITION_SIZE
    trade_value = account_balance * size
    return trade_value

def within_daily_loss_limit(starting_balance, current_balance):
    loss_pct = (starting_balance - current_balance) / starting_balance
    return loss_pct < config.MAX_DAILY_LOSS
