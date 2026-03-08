import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.market_data import load_local_data
from backtest.backtest_engine import run_backtest, calc_metrics, buy_and_hold
import config

INITIAL_CASH = 100_000
TRAIN_END    = "2021-12-31"
TEST_START   = "2022-01-01"

print(f"\n{'='*72}")
print(f"  WALK-FORWARD TEST")
print(f"  Train: 2018 → {TRAIN_END}   |   Out-of-sample: {TEST_START} → now")
print(f"{'='*72}\n")

header = f"  {'Symbol':<6}  {'Period':<12}  {'Trades':>6}  {'WR%':>5}  {'PF':>6}  {'DD%':>6}  {'Return%':>8}  {'B&H%':>8}"
divider = f"  {'-'*70}"

print(header)
print(divider)

for symbol in config.SYMBOLS:
    try:
        data = load_local_data(symbol)
        data.index = data.index.astype("datetime64[ns]")

        train_data = data[data.index <= TRAIN_END]
        test_data  = data[data.index >= TEST_START]

        for label, subset in [("IN-SAMPLE ", train_data), ("OUT-SAMPLE", test_data)]:
            if len(subset) < 210:
                print(f"  {symbol:<6}  {label}  (not enough data)")
                continue

            final, trades, pv = run_backtest(subset, initial_cash=INITIAL_CASH)
            if not trades:
                print(f"  {symbol:<6}  {label}  (no trades)")
                continue

            m   = calc_metrics(trades, INITIAL_CASH, final, pv)
            bah = buy_and_hold(subset)
            ok  = "✓" if m["profit_factor"] >= 1.3 and m["max_drawdown"] <= 15 else "✗"

            print(f"  {symbol:<6}  {label}  {m['total_trades']:>6}  "
                  f"{m['win_rate']:>5}  {m['profit_factor']:>6}  "
                  f"{m['max_drawdown']:>6}  {m['total_return']:>8}  {bah:>8}  {ok}")

        print(divider)

    except FileNotFoundError:
        print(f"  {symbol:<6}  no local data\n")
    except Exception as e:
        print(f"  {symbol:<6}  ERROR: {e}\n")

print()
