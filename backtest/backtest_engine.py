import pandas as pd
import numpy as np
import os
import contextlib
from strategies.ma_crossover import generate_signal
from core.atr import atr_stop
from core.position_sizer import calculate_position_size

COMMISSION = 0.001   # 0.1% per trade
SLIPPAGE   = 0.0005  # 0.05% per trade
RISK_PCT   = 0.01    # 1% account risk per trade
ATR_MULT   = 2.0

@contextlib.contextmanager
def _silent():
    with open(os.devnull, "w") as null:
        with contextlib.redirect_stdout(null):
            yield

def _apply_costs(price, side):
    slip = price * SLIPPAGE
    comm = price * COMMISSION
    return price + slip + comm if side == "BUY" else price - slip - comm

def run_backtest(data, initial_cash=100000, symbol="???"):
    cash = initial_cash
    position = 0
    entry_price = 0
    entry_date = None
    portfolio_values = []
    trades = []

    # Need at least 201 bars: 200 for MA200 + 1 so signal uses yesterday,
    # execution uses today's OPEN (no look-ahead bias)
    for i in range(201, len(data)):
        signal_data = data.iloc[:i]          # everything UP TO yesterday's close
        exec_price  = float(data["Open"].iloc[i])  # enter/exit at TODAY's open
        date        = data.index[i]

        # Mark-to-market at today's close for equity curve
        close_price  = float(data["Close"].iloc[i])
        portfolio_val = cash + position * close_price
        portfolio_values.append((date, portfolio_val))

        try:
            with _silent():
                signal = generate_signal(signal_data)
        except Exception:
            continue

        if signal == "BUY" and position == 0:
            try:
                with _silent():
                    stop, atr = atr_stop(signal_data, multiplier=ATR_MULT)
            except Exception:
                stop = exec_price * 0.98
            shares = calculate_position_size(portfolio_val, RISK_PCT, exec_price, stop)
            cost = _apply_costs(exec_price, "BUY")
            total_cost = shares * cost
            if shares > 0 and total_cost <= cash:
                cash -= total_cost
                position = shares
                entry_price = cost
                entry_date = date

        elif signal == "SELL" and position > 0:
            proceeds_per = _apply_costs(exec_price, "SELL")
            pnl = position * (proceeds_per - entry_price)
            pct = (proceeds_per - entry_price) / entry_price * 100
            duration = (date - entry_date).days
            cash += position * proceeds_per
            trades.append({
                "entry_date":  entry_date,
                "exit_date":   date,
                "entry_price": round(entry_price, 4),
                "exit_price":  round(proceeds_per, 4),
                "shares":      position,
                "pnl":         round(pnl, 2),
                "pct":         round(pct, 4),
                "duration":    duration,
                "win":         pnl > 0,
            })
            position = 0
            entry_price = 0
            entry_date = None

    final_price     = float(data["Close"].iloc[-1])
    final_portfolio = cash + position * final_price
    return final_portfolio, trades, portfolio_values


def buy_and_hold(data, initial_cash=100000):
    start = float(data["Close"].iloc[201])
    end   = float(data["Close"].iloc[-1])
    return round((end - start) / start * 100, 2)


def calc_metrics(trades, initial_cash, final_portfolio, portfolio_values):
    if not trades:
        return {"error": "no completed trades"}

    pnls     = [t["pnl"] for t in trades]
    wins     = [p for p in pnls if p > 0]
    losses   = [p for p in pnls if p <= 0]
    duration = [t["duration"] for t in trades]

    win_rate      = len(wins) / len(pnls) * 100
    avg_win       = np.mean(wins)   if wins   else 0
    avg_loss      = np.mean(losses) if losses else 0
    gross_profit  = sum(wins)
    gross_loss    = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    avg_duration  = int(np.mean(duration)) if duration else 0

    values = [v for _, v in portfolio_values]
    peak, max_dd = values[0], 0
    for v in values:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd: max_dd = dd

    vals_series   = pd.Series(values)
    daily_ret     = vals_series.pct_change().dropna()
    sharpe        = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)
                     if daily_ret.std() > 0 else 0)
    total_return  = (final_portfolio - initial_cash) / initial_cash * 100

    return {
        "total_trades":  len(trades),
        "avg_duration":  avg_duration,
        "win_rate":      round(win_rate, 1),
        "avg_win":       round(avg_win, 2),
        "avg_loss":      round(avg_loss, 2),
        "profit_factor": round(profit_factor, 3),
        "max_drawdown":  round(max_dd, 2),
        "sharpe":        round(sharpe, 3),
        "total_return":  round(total_return, 2),
        "final_balance": round(final_portfolio, 2),
    }
