# Portfolio Strategy Comparison

Current baseline for portfolio-management strategy discussion:

- initial portfolio: `0 BTC / 0 ETH / 10000 DAI`
- cadence: `weekly` (`7d`)
- starts: quarterly from `2020-01-01`
- shortest late window excluded: `2026-04-01`
- market data updated through `2026-05-05`

## Caps

### `100 DAI` per buy trade

- top 3 by mean return:
  1. `btc_defensive_eth_aggressive` — `117.54%`
  2. `static_50_50_rebalance` — `111.17%`
  3. `narrow_cash_band_rebalance` — `103.10%`
- negative windows begin earlier and are more frequent
- late-cycle windows are generally shallow to moderately negative rather than catastrophic

### `500 DAI` per buy trade

- top 3 by mean return:
  1. `btc_defensive_eth_aggressive` — `168.86%`
  2. `static_50_50_rebalance` — `154.08%`
  3. `drawdown_tilt_rebalance` — `144.68%`
- materially stronger than the `100 DAI` cap
- `drawdown_tilt_rebalance` re-enters the top 3 once the cap loosens

## Fresh conclusions

- The `all DAI` starting point makes the strategy differences more meaningful, because the strategies now control initial deployment from cash instead of just rebalancing an already-risky portfolio.
- `btc_defensive_eth_aggressive` remains the best overall strategy under both caps.
- `static_50_50_rebalance` is still the best simple benchmark and stays close to the leader.
- Tight caps hurt the more opportunistic strategies disproportionately; at `100 DAI`, the top strategies bunch together more tightly.
- With `500 DAI`, tactical deployment helps enough for `drawdown_tilt_rebalance` to beat the narrower cash-band strategy.
- Negative quarterly start windows definitely exist for both cap settings.
- Under `100 DAI`, the first negative windows for the top strategies already appear in `2024-10-01`.
- Under `500 DAI`, the extra deployment boosts upside but also deepens some late-cycle downside windows.

## Where To Look

- [cap100/weekly_top3_summary.md](cap100/weekly_top3_summary.md)
- [cap100/strategy_catalog.md](cap100/strategy_catalog.md)
- [cap100/negative_windows.md](cap100/negative_windows.md)
- [cap500/weekly_top3_summary.md](cap500/weekly_top3_summary.md)
- [cap500/strategy_catalog.md](cap500/strategy_catalog.md)
- [cap500/negative_windows.md](cap500/negative_windows.md)

Each cap folder also contains:

- quarterly equity-curve charts
- weekly allocation/trade charts for the top 3 strategies
- raw CSV, Markdown, and text outputs
- a manifest for reproducibility
