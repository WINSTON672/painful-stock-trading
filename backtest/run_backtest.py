import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # no display needed
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from data.market_data import load_local_data
from backtest.backtest_engine import run_backtest, calc_metrics, buy_and_hold
import config

INITIAL_CASH = 100_000
SYMBOLS      = config.SYMBOLS
CHART_PATH   = "logs/equity_curve.png"

os.makedirs("logs", exist_ok=True)

print(f"\n{'='*68}")
print(f"  BACKTEST  |  MA20/50/200 + RSI  |  Comm 0.1%  |  Slip 0.05%")
print(f"  No look-ahead: signal on yesterday's close → execute at today's open")
print(f"  Starting cash per symbol: ${INITIAL_CASH:,.0f}")
print(f"{'='*68}\n")

all_results   = []
equity_curves = {}   # symbol → pd.Series of portfolio value

for symbol in SYMBOLS:
    try:
        data  = load_local_data(symbol)
        final, trades, pv = run_backtest(data, initial_cash=INITIAL_CASH, symbol=symbol)
        m     = calc_metrics(trades, INITIAL_CASH, final, pv)
        bah   = buy_and_hold(data, initial_cash=INITIAL_CASH)
        m["symbol"] = symbol
        m["buy_hold"] = bah
        all_results.append(m)

        # Store equity curve as Series indexed by date
        dates  = [d for d, _ in pv]
        values = [v for _, v in pv]
        equity_curves[symbol] = pd.Series(values, index=pd.DatetimeIndex(dates))

        print(f"── {symbol} {'─'*(46-len(symbol))}")
        if "error" in m:
            print(f"  {m['error']}\n"); continue

        print(f"  Trades:          {m['total_trades']}  (avg {m['avg_duration']} days/trade)")
        print(f"  Win rate:        {m['win_rate']}%")
        print(f"  Avg win:         ${m['avg_win']:,.2f}")
        print(f"  Avg loss:        ${m['avg_loss']:,.2f}")
        print(f"  Profit factor:   {m['profit_factor']}")
        print(f"  Max drawdown:    {m['max_drawdown']}%")
        print(f"  Sharpe ratio:    {m['sharpe']}")
        print(f"  Strategy return: {m['total_return']}%")
        print(f"  Buy & hold:      {bah}%")
        print(f"  Final balance:   ${m['final_balance']:,.2f}")
        print()

    except FileNotFoundError:
        print(f"── {symbol}: no local data\n")
    except Exception as e:
        print(f"── {symbol}: ERROR — {e}\n")

# ── Summary table ────────────────────────────────────────────────
print(f"{'='*68}")
print(f"  {'Symbol':<6}  {'Trades':>6}  {'AvgDays':>7}  {'WR%':>5}  {'PF':>6}  "
      f"{'DD%':>6}  {'Strat%':>7}  {'B&H%':>7}  OK?")
print(f"  {'-'*62}")
for r in all_results:
    if "error" in r: continue
    ok = "✓" if r["profit_factor"] >= 1.3 and r["max_drawdown"] <= 15 else "✗"
    print(f"  {r['symbol']:<6}  {r['total_trades']:>6}  {r['avg_duration']:>7}  "
          f"{r['win_rate']:>5}  {r['profit_factor']:>6}  {r['max_drawdown']:>6}  "
          f"{r['total_return']:>7}  {r['buy_hold']:>7}  {ok}")

# ── Portfolio simulation (equal capital split) ───────────────────
print(f"\n{'='*68}")
print(f"  PORTFOLIO SIMULATION  (${INITIAL_CASH:,.0f} split equally across {len(SYMBOLS)} symbols)")
print(f"{'='*68}")

if equity_curves:
    per_symbol = INITIAL_CASH / len(equity_curves)
    combined   = None
    for sym, curve in equity_curves.items():
        scaled = curve * (per_symbol / INITIAL_CASH)
        combined = scaled if combined is None else combined.add(scaled, fill_value=0)

    port_return = (combined.iloc[-1] - INITIAL_CASH) / INITIAL_CASH * 100
    peak, max_dd = combined.iloc[0], 0
    for v in combined:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd: max_dd = dd

    print(f"  Portfolio return: {port_return:.1f}%")
    print(f"  Max drawdown:     {max_dd:.2f}%")
    print(f"  Final value:      ${combined.iloc[-1]:,.2f}")

# ── Equity curve chart ───────────────────────────────────────────
fig, ax = plt.subplots(figsize=(13, 6))
fig.patch.set_facecolor("#1a1a2e")
ax.set_facecolor("#16213e")

colours = ["#4fc3f7", "#a5d6a7", "#ffcc80", "#cf6679", "#b39ddb"]
for (sym, curve), col in zip(equity_curves.items(), colours):
    ax.plot(curve.index, curve.values, label=sym, color=col, linewidth=1.5)

if equity_curves:
    ax.plot(combined.index, combined.values,
            label="Portfolio", color="#ffffff", linewidth=2.5, linestyle="--")

ax.axhline(INITIAL_CASH, color="#555", linewidth=1, linestyle=":")
ax.set_title("Equity Curve — MA20/50/200 + RSI Strategy (2018–now)",
             color="#e0e0e0", fontsize=13, pad=12)
ax.set_ylabel("Portfolio Value ($)", color="#aaa")
ax.set_xlabel("Date", color="#aaa")
ax.tick_params(colors="#aaa")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.legend(facecolor="#0f3460", edgecolor="#333", labelcolor="#e0e0e0", fontsize=9)
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
for spine in ax.spines.values():
    spine.set_edgecolor("#333")

plt.tight_layout()
plt.savefig(CHART_PATH, dpi=150, facecolor=fig.get_facecolor())
plt.close()
print(f"\n  Equity curve saved → {CHART_PATH}")
print()
