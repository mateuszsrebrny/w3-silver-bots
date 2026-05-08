# Budgeted Scenario Comparison

This note compares three weekly budgeted-portfolio scenarios that were run after the budgeted strategy cleanup.

The compared scenarios are:

- [`10000 DAI / 250 buy cap`](../20260508-152919)
- [`15000 DAI / 500 buy cap`](../20260508-152944)
- [`15000 DAI / 250 buy cap`](../20260508-054922)

All scenarios use:

- initial portfolio of `0 BTC / 0 ETH / <DAI amount>`
- weekly cadence (`7d`)
- quarterly starts from `2020-01-01`
- no sell cap
- no withdrawals

## Summary Table

Scenario | Strategy | Mean Return % | Worst Return % | Best Return % | Minimum DAI | Max DAI Used
--- | --- | ---: | ---: | ---: | ---: | ---:
`10000 / 250` | `budgeted_static_50_50_rebalance` | `100.71` | `-17.15` | `693.45` | `983.23` | `9016.77`
`10000 / 250` | `budgeted_drawdown_tilt_rebalance` | `105.78` | `-5.44` | `605.91` | `0.00` | `10000.00`
`10000 / 250` | `budgeted_btc_defensive_eth_aggressive` | `97.50` | `-15.14` | `660.35` | `0.00` | `10000.00`
`15000 / 500` | `budgeted_static_50_50_rebalance` | `114.36` | `-14.71` | `777.67` | `1447.62` | `13552.38`
`15000 / 500` | `budgeted_drawdown_tilt_rebalance` | `122.15` | `-7.26` | `730.71` | `0.00` | `15000.00`
`15000 / 500` | `budgeted_btc_defensive_eth_aggressive` | `111.35` | `-17.77` | `809.47` | `0.00` | `15000.00`
`15000 / 250` | `budgeted_static_50_50_rebalance` | `81.20` | `-12.15` | `521.95` | `1674.54` | `13325.46`
`15000 / 250` | `budgeted_drawdown_tilt_rebalance` | `86.07` | `-3.63` | `455.16` | `0.00` | `15000.00`
`15000 / 250` | `budgeted_btc_defensive_eth_aggressive` | `82.76` | `-10.60` | `508.65` | `0.00` | `15000.00`

## Main Takeaways

- Increasing starting DAI from `10000` to `15000` helps preserve optionality only in the trivial sense that there is more money available.
- For the two more aggressive budgeted strategies, more starting DAI does **not** create a meaningful reserve by itself:
  - `budgeted_drawdown_tilt_rebalance` can still spend all available DAI
  - `budgeted_btc_defensive_eth_aggressive` can still spend all available DAI
- Lowering the buy cap from `500` to `250` slows deployment, but does **not** guarantee dry powder:
  - it improves pacing
  - it does not prevent full deployment in stronger strategies
- `budgeted_static_50_50_rebalance` is the only one of the three that consistently leaves some cash reserve by behavior alone.
- If the real goal is “always keep meaningful cash for a deeper bear,” a simple buy cap is not enough.

## Recommendation From This Batch

If the priority is:

- **best pacing without adding new reserve logic**:
  - `10000 DAI / 250 buy cap`
- **best upside among the budgeted scenarios tested here**:
  - `15000 DAI / 500 buy cap`
- **actual dry-powder preservation as a first-class behavior**:
  - add a reserve-aware rule instead of only tweaking the cap

That is the motivation for the next step: reserve-aware spending below a chosen DAI reserve threshold.
