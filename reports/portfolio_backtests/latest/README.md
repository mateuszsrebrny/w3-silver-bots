# Portfolio Backtests: Latest

This directory is the current "working view" of the portfolio-management backtests.

The current baseline behind these files is:

- initial portfolio: `0 BTC / 0 ETH / 10000 DAI`
- cadence: `weekly` (`7d`)
- start dates: quarterly from `2020-01-01`
- short final start `2026-04-01` excluded
- market data updated through `2026-05-05`

If you want immutable historical snapshots, use the timestamped run directories under `reports/portfolio_backtests/`.

## What To Read First

- [cap_comparison.md](cap_comparison.md)
  - top-level comparison of the current `100 DAI` and `500 DAI` max-buy variants
  - the best place to start if you want the current conclusions

- [weekly_top3_summary.md](weekly_top3_summary.md)
  - summary for the root `latest/` view
  - shows the top 3 strategies for the currently mirrored root result set

- [strategy_catalog.md](strategy_catalog.md)
  - strategy-by-strategy table
  - shows all tested quarterly starting dates
  - includes:
    - total return
    - annualized return
    - max drawdown
    - ending portfolio value
    - whether the window finished below zero

- [negative_windows.md](negative_windows.md)
  - only the start windows that ended with negative total return
  - useful for finding fragile entry points quickly

## Main Data Files

- [portfolio_strategy_results.csv](portfolio_strategy_results.csv)
  - machine-friendly raw result table
  - use for spreadsheet work, sorting, or custom charts

- [portfolio_strategy_results.md](portfolio_strategy_results.md)
  - readable Markdown export of the same result table

- [portfolio_strategy_results.txt](portfolio_strategy_results.txt)
  - plain fixed-width text table for terminal reading

- [manifest.json](manifest.json)
  - metadata for the root `latest/` snapshot
  - includes the effective parameters, data files, and git commit

## Chart Types

### Quarterly Equity Curves

Files named like:

- `portfolio_value_2020-01-01_7d.svg`

These compare multiple strategies on one chart for one start date.

How to read them:

- x-axis: time
- y-axis: total portfolio value in USD
- each line: one strategy
- use these to compare overall growth paths and drawdown shape between strategies

### Weekly Allocation/Trade Charts

Files named like:

- `weekly_strategy_static_50_50_rebalance_2020-01-01.svg`

These are single-strategy charts for one start date.

How to read them:

- top panel:
  - stacked portfolio value split between `DAI`, `ETH`, and `BTC`
- middle panel:
  - signed weekly `BTC` trade notional in USD
  - positive bar = buy
  - negative bar = sell
- bottom panel:
  - signed weekly `ETH` trade notional in USD
  - positive bar = buy
  - negative bar = sell

All three panels are synchronized on the same weekly timeline.

## Cap-Specific Folders

- [cap100](cap100)
  - full artifact set for `max_buy_trade_dai = 100`

- [cap500](cap500)
  - full artifact set for `max_buy_trade_dai = 500`

Each of those folders contains:

- its own `weekly_top3_summary.md`
- its own `strategy_catalog.md`
- its own `negative_windows.md`
- quarterly equity-curve charts
- weekly allocation/trade charts
- raw CSV/Markdown/text results
- a manifest

Use these folders when you want exact cap-specific conclusions without mixing them with the root `latest/` summary.

## Interpreting The Numbers

- `Return %`
  - total portfolio gain/loss versus the starting `10000 DAI`

- `Annualized %`
  - normalized return per year
  - useful across different start lengths
  - less trustworthy for very short windows

- `Max Drawdown %`
  - worst peak-to-trough portfolio decline during the run

- `Negative?`
  - whether that tested start window ended below the starting capital

## Important Caveats

- These are simplified backtests, not executable historical trading reconstructions.
- No tax model is included.
- Execution slippage is simplified.
- The buy cap applies per buy trade, not necessarily as a total weekly budget across both assets combined.
