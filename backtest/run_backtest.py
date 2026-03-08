import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.market_data import load_local_data
from backtest.backtest_engine import run_backtest, calc_metrics
import config

INITIAL_CASH = 100_000
SYMBOLS = config.SYMBOLS

print(f"\n{'='*60}")
print(f"  BACKTEST — MA20/50/200 + RSI  |  Commission 0.1%  |  Slippage 0.05%")
print(f"  Starting cash: ${INITIAL_CASH:,.0f}")
print(f"{'='*60}\n")

all_results = []

for symbol in SYMBOLS:
    try:
        data = load_local_data(symbol)
        final, trades, pv = run_backtest(data, initial_cash=INITIAL_CASH, symbol=symbol)
        metrics = calc_metrics(trades, INITIAL_CASH, final, pv)
        metrics["symbol"] = symbol
        all_results.append(metrics)

        print(f"── {symbol} ───────────────────────────────────")
        if "error" in metrics:
            print(f"  {metrics['error']}\n")
            continue
        print(f"  Trades:         {metrics['total_trades']}")
        print(f"  Win rate:       {metrics['win_rate']}%")
        print(f"  Avg win:        ${metrics['avg_win']:,.2f}")
        print(f"  Avg loss:       ${metrics['avg_loss']:,.2f}")
        print(f"  Profit factor:  {metrics['profit_factor']}")
        print(f"  Max drawdown:   {metrics['max_drawdown']}%")
        print(f"  Sharpe ratio:   {metrics['sharpe']}")
        print(f"  Total return:   {metrics['total_return']}%")
        print(f"  Final balance:  ${metrics['final_balance']:,.2f}")
        print()

    except FileNotFoundError:
        print(f"── {symbol}: no local data — run data/download_data.py first\n")
    except Exception as e:
        print(f"── {symbol}: ERROR — {e}\n")

print(f"{'='*60}")
print("  SUMMARY")
print(f"{'='*60}")
for r in all_results:
    if "error" not in r:
        flag = "✓" if r["profit_factor"] >= 1.3 and r["max_drawdown"] <= 15 else "✗"
        print(f"  {flag}  {r['symbol']:<6}  PF={r['profit_factor']:<6}  DD={r['max_drawdown']}%  "
              f"WR={r['win_rate']}%  Return={r['total_return']}%")
print()
