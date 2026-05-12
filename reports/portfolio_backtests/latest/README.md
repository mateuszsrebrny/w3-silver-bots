# Portfolio Backtests: Latest

This directory is the current working view of the portfolio-management backtests.

The current mirrored snapshot behind these files is:

- initial portfolio: `0 BTC / 0 ETH / 10000 DAI`
- cadences: `1d, 2d, 3d, 5d, 7d`
- start dates: `2020-01-01, 2020-04-01, 2020-07-01, 2020-10-01, 2021-01-01, 2021-04-01, 2021-07-01, 2021-10-01, 2022-01-01, 2022-04-01, 2022-07-01, 2022-10-01, 2023-01-01, 2023-04-01, 2023-07-01, 2023-10-01, 2024-01-01, 2024-04-01, 2024-07-01, 2024-10-01, 2025-01-01, 2025-04-01, 2025-07-01, 2025-10-01, 2026-01-01`
- market data updated through `2026-05-09`
- buy cap per rebalance step: `400 DAI`
- sell cap per rebalance step: `none`
- reserve floor: `2000 DAI`
- reserve buy scale below floor: `0.50`
- reserve deep-drawdown buy scale below half-floor: `0.25`

The primary discussion in this directory now focuses on the **budgeted** strategies only:

- `budgeted_static_50_50_rebalance`
- `budgeted_drawdown_tilt_rebalance`
- `budgeted_btc_defensive_eth_aggressive`

Those are the strategies intended for realistic capped live execution.

If you want immutable historical snapshots, use the timestamped run directories under `reports/portfolio_backtests/`.

## What To Read First

- [weekly_top3_summary.md](weekly_top3_summary.md)
  - current ranking for the weekly (`7d`) snapshot only
  - best place to start if you want the operator-facing weekly conclusions

- [strategy_catalog.md](strategy_catalog.md)
  - strategy-by-strategy table across all tested intervals and quarterly starts
  - includes interval, total return, annualized return, drawdown, ending value, and whether the window finished below zero

- [negative_windows.md](negative_windows.md)
  - only the start windows that ended with negative total return
  - useful for finding fragile entry points quickly

- [manifest.json](manifest.json)
  - exact parameters, data files, and git commit for this mirrored snapshot

## Main Data Files

- [portfolio_strategy_results.csv](portfolio_strategy_results.csv)
  - machine-friendly raw result table
  - includes all tested strategies and intervals

- [portfolio_strategy_results.md](portfolio_strategy_results.md)
  - readable Markdown export of the same full result table

- [portfolio_strategy_results.txt](portfolio_strategy_results.txt)
  - plain fixed-width text table for terminal reading

## Chart Types

### Quarterly Equity Curves

Files named like:

- `portfolio_value_2020-01-01_7d.svg`

These compare the **primary budgeted strategies** on one chart for one `(start, interval)` scenario.

### Weekly Allocation/Trade Charts

Files named like:

- `weekly_strategy_budgeted_btc_defensive_eth_aggressive_2020-01-01.svg`

These are single-strategy charts for one weekly start window.

## Important Caveats

- These are simplified backtests, not executable historical trading reconstructions.
- No tax model is included.
- Execution slippage is simplified.
- Weekly summaries rank only the `7d` runs, even when the raw tables include multiple intervals.
- The budgeted strategies here also include the configured DAI reserve behavior from `manifest.json`.
