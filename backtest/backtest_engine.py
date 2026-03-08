import pandas as pd
import numpy as np
import os
import contextlib
from strategies.ma_crossover import generate_signal

@contextlib.contextmanager
def _silent():
    with open(os.devnull, "w") as null:
        with contextlib.redirect_stdout(null):
            yield
from core.atr import atr_stop
from core.position_sizer import calculate_position_size

COMMISSION = 0.001   # 0.1% per trade
SLIPPAGE   = 0.0005  # 0.05% per trade
RISK_PCT   = 0.01    # 1% account risk per trade
ATR_MULT   = 2.0

def _apply_costs(price, side):
    """Apply slippage and commission to execution price."""
    slip = price * SLIPPAGE
    comm = price * COMMISSION
    if side == "BUY":
        return price + slip + comm   # pay more when buying
    else:
        return price - slip - comm   # receive less when selling

def run_backtest(data, initial_cash=100000, symbol="???"):
    cash = initial_cash
    position = 0    # shares held
    entry_price = 0
    entry_date = None
    portfolio_values = []
    trades = []

    # Need at least 200 bars for MA200
    for i in range(200, len(data)):
        slice_data = data.iloc[:i]
        price_raw = float(data["Close"].iloc[i])
        date = data.index[i]

        # Portfolio value today
        portfolio_val = cash + position * price_raw
        portfolio_values.append((date, portfolio_val))

        try:
            with _silent():
                signal = generate_signal(slice_data)
        except Exception:
            continue

        if signal == "BUY" and position == 0:
            # ATR stop + position size
            try:
                stop, atr = atr_stop(slice_data, multiplier=ATR_MULT)
            except Exception:
                stop = price_raw * 0.98
            shares = calculate_position_size(portfolio_val, RISK_PCT, price_raw, stop)
            cost = _apply_costs(price_raw, "BUY")
            total_cost = shares * cost
            if shares > 0 and total_cost <= cash:
                cash -= total_cost
                position = shares
                entry_price = cost
                entry_date = date

        elif signal == "SELL" and position > 0:
            proceeds_per_share = _apply_costs(price_raw, "SELL")
            proceeds = position * proceeds_per_share
            pnl = position * (proceeds_per_share - entry_price)
            pct = (proceeds_per_share - entry_price) / entry_price * 100
            cash += proceeds
            trades.append({
                "entry_date":  entry_date,
                "exit_date":   date,
                "entry_price": round(entry_price, 4),
                "exit_price":  round(proceeds_per_share, 4),
                "shares":      position,
                "pnl":         round(pnl, 2),
                "pct":         round(pct, 4),
                "win":         pnl > 0,
            })
            position = 0
            entry_price = 0
            entry_date = None

    # Close any open position at last price
    final_price = float(data["Close"].iloc[-1])
    final_portfolio = cash + position * final_price

    return final_portfolio, trades, portfolio_values


def calc_metrics(trades, initial_cash, final_portfolio, portfolio_values):
    if not trades:
        return {"error": "no completed trades"}

    pnls   = [t["pnl"] for t in trades]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate      = len(wins) / len(pnls) * 100
    avg_win       = np.mean(wins)   if wins   else 0
    avg_loss      = np.mean(losses) if losses else 0
    gross_profit  = sum(wins)
    gross_loss    = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Max drawdown
    values = [v for _, v in portfolio_values]
    peak = values[0]
    max_dd = 0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe (annualised, daily returns, risk-free ~0)
    vals_series = pd.Series(values)
    daily_returns = vals_series.pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)
              if daily_returns.std() > 0 else 0)

    total_return = (final_portfolio - initial_cash) / initial_cash * 100

    return {
        "total_trades":   len(trades),
        "win_rate":       round(win_rate, 1),
        "avg_win":        round(avg_win, 2),
        "avg_loss":       round(avg_loss, 2),
        "profit_factor":  round(profit_factor, 3),
        "max_drawdown":   round(max_dd, 2),
        "sharpe":         round(sharpe, 3),
        "total_return":   round(total_return, 2),
        "final_balance":  round(final_portfolio, 2),
    }
