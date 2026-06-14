# Curated Portfolio Backtest: Reserve 3000, Step 300

This curated report set evaluates the portfolio DCA strategies using the live-style parameters used for weekly decisions in June 2026.

- generated run: [`20260614-050035`](20260614-050035/)
- market data through: `2026-06-13`
- initial portfolio buckets: `0.07780312 BTC / 3.067701173484763094131416718 ETH / 11919.872908084459324919 DAI`
- cadence: weekly only (`7d`)
- start windows: quarterly starts from `2020-01-01` through `2026-01-01`
- buy cap: `300 DAI` per rebalance step
- reserve floor: `3000 DAI`
- reserve buy scale: `0.50`
- deep-reserve buy scale: `0.25`

Start with:

- [`weekly_top3_summary.md`](20260614-050035/weekly_top3_summary.md) for the operator-facing weekly ranking.
- [`strategy_catalog.md`](20260614-050035/strategy_catalog.md) for per-strategy return and drawdown tables.
- [`manifest.json`](20260614-050035/manifest.json) for exact generation parameters.

Current weekly ranking summary:

| Rank | Strategy | Mean Return % | Min Return % | Max Return % |
| --- | --- | ---: | ---: | ---: |
| 1 | `budgeted_drawdown_tilt_rebalance` | 81.53 | -43.50 | 539.38 |
| 2 | `budgeted_ethbtc_trend_filtered_drawdown_tilt` | 78.73 | -43.37 | 539.27 |
| 3 | `budgeted_static_50_50_rebalance` | 76.26 | -43.15 | 601.68 |

The moving `latest/` mirror is intentionally ignored and not committed; this directory keeps an immutable generated run instead.
