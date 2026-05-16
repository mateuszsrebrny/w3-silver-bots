# LP Backtest Findings

This report uses a simplified constant-product 50/50 LP model with fixed fee-yield assumptions and daily market closes through 2026-05-09.

## Scope

- `WBTC/WETH` tested with a fixed `26% APR`
- `USDT/WETH` tested with a fixed `45% APR`
- Benchmarks:
  - hold asset A only
  - hold asset B only
  - hold the pair as a passive `50/50` basket

## Main Findings

- `WBTC/WETH` is the more credible LP candidate when the user intends to keep both assets anyway.
- Against a passive `50/50` hold, the `WBTC/WETH` LP only needed low single-digit APR in the tested windows:
  - about `0.05%` to `3.20%`
- Against pure `WBTC`, the required APR was more regime-sensitive:
  - `-3.26%`, `-1.34%`, `15.03%`, `17.38%` across the tested start dates
- Against pure `WETH`, the required APR stayed modest or negative:
  - `4.10%`, `1.44%`, `-9.09%`, `-10.98%`
- `USDT/WETH` behaves more like a yield-vs-upside trade:
  - it can beat passive `50/50`
  - but it gives up more directional ETH upside than `WBTC/WETH`

## Interpretation

- If the real alternative is holding both `WBTC` and `WETH` separately, then `WBTC/WETH` LP only needs a few percent sustained yield to compete.
- If realized LP yield falls back toward the same `1%` to `2%` range as single-sided parking, the operational overhead and uncertainty likely are not worth it.
- The important variable is not the headline APY snapshot, but the average realized yield over the period the position stays open.

## Caveats

- This is not a full Beefy or Velodrome strategy simulation.
- The model assumes:
  - a plain constant-product 50/50 LP
  - fixed APR or APY through the whole holding period
  - no token incentives changing over time
  - no gas, re-entry, withdrawal, or reward-token volatility
- Use this report as a threshold / break-even tool, not as a precise production forecast.
