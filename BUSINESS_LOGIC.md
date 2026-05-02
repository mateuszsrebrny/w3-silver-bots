# Business Logic And Strategy Notes

## Why This Repo Exists

There are really two business problems here:

1. know what the live on-chain portfolio currently contains and what it is worth
2. research systematic ways to deploy and extract capital across BTC, ETH, and DAI

The repo therefore has two different "modes of truth":

- live wallet mode:
  - actual balances
  - route-based current quotes

- research mode:
  - simplified historical market model
  - daily candle-driven decisions

These should not be confused.

## Live Tracker Business Logic

### Goal

Track a wallet across several EVM chains and present:

- held amount per token
- current value in `USDC`

### Asset Scope

Tracked assets currently come from the MetaMask-like portfolio scope that was discussed during development:

- Polygon assets such as `POL`, `AAVE`, `LINK`, `GHST`, `BAL`
- Optimism assets such as `ETH`, `VELO`
- Ethereum assets such as `ETH`, `DAI`, `WBTC`, `GLM`, `WSTETH`, `WTAO`, `aDAI`
- Arbitrum assets such as `ETH`, `aARB`

This is not intended to be a universal portfolio indexer. It is a curated set of assets relevant to the wallet owner.

### Pricing Logic

Current live valuation uses KyberSwap route discovery because it handles:

- venue aggregation
- path optimization
- better token coverage than hand-built single-DEX routing

The tracker values everything in `USDC`, not `DAI`.

That choice was deliberate:

- avoids an unnecessary `USDC -> DAI` final hop
- reduces tiny-balance rounding issues
- matches how most quote infrastructure behaves

## Historical Data Business Logic

### Why BTC-USD And ETH-USD

For strategy research, the repo uses:

- `BTC-USD` as the economic proxy for `WBTC`
- `ETH-USD` for Ethereum exposure

Reason:

- strategy cadence is daily/weekly style
- the aim is to model macro crypto exposure, not reconstruct historical DEX route execution
- local reproducible candles are more valuable here than fragile historical DeFi execution assumptions

### Why Daily Candles

The current decision horizon is:

- DCA
- weekly or low-frequency rotation
- medium-horizon regime logic

Daily candles are enough for:

- MA filters
- drawdowns
- trailing returns
- regime classification

They are not enough for:

- intraday execution timing
- realistic "buy sometime Sunday but not at a fixed minute" modeling

That would require hourly or lower data later.

## DCA Backtests

The DCA framework is for recurring-contribution questions such as:

- if I keep adding cash, should I buy regardless of trend?
- should I buy only above MA or below MA?
- should I scale contributions up on dips?
- should I split contributions between BTC and ETH?

### Strategy Families

#### Single-Asset

- fixed recurring buy
- MA trend filter
- MA dip filter
- MA-scaled buy sizing
- drawdown-scaled buy sizing

#### Dual-Asset

- BTC-only
- ETH-only
- equal split
- stronger-asset momentum
- weaker-asset contrarian
- MA-relative BTC/ETH selectors
- BTC core with conditional ETH overlay

### Interpretation

These backtests answer:

- what was a good use of new incoming cash?

They do not answer:

- how to manage a finished portfolio with no more contributions
- how to fund living expenses
- how to gradually de-risk into stable assets

That is why the portfolio-management layer was added later.

## Portfolio-Management Backtests

### Goal

Model a portfolio with only three buckets:

- `BTC`
- `ETH`
- `DAI`

The simplified business objective is:

- accumulate more crypto when markets are weak
- hold a meaningful BTC/ETH mix long term
- rotate part of the gains back to `DAI` when markets are rich
- eventually use `DAI` withdrawals to reduce work dependence

### Deliberate Simplifications

- `aDAI` is treated as plain `DAI`
- no lending yield
- no taxes
- no execution slippage
- no partial fills
- no exchange/DEX fragmentation

Those simplifications are intentional because the first-order question is strategy shape, not accounting polish.

### Portfolio Strategy Families

#### Static 50/50 Rebalance

Intent:

- maintain a stable risk mix
- keep a fixed cash bucket

Interpretation:

- benchmark
- useful because many fancier rules should be judged against this, not against fantasy timing

#### Cash-Band Rebalance

Intent:

- hold more `DAI` in expensive regimes
- hold less `DAI` in cheap regimes

Issue observed:

- broad cash bands were too defensive in the long 2020+ bull path
- they sold too much risk too early

#### Drawdown-Tilt Rebalance

Intent:

- deploy more aggressively in deeper drawdowns
- tilt toward the more discounted asset

Business interpretation:

- this is the closest implemented strategy to "buy when things are down"

#### BTC-Defensive / ETH-Aggressive

Intent:

- keep BTC as the defensive crypto anchor
- allow more ETH only when ETH strength justifies it

Business interpretation:

- this reflects the view that BTC is the safer crypto beta
- ETH should still be owned, but not treated symmetrically in every regime

## What The Current Results Mean

### Broad Pattern So Far

- for recurring DCA research, plain BTC exposure often dominates more complicated filters
- for portfolio-management research, the best strategy depends materially on the start date
- strategies that keep both BTC and ETH but lean conditionally often do better than naive symmetric cash-band logic

### Why Start Date Matters

The tested start dates span very different crypto regimes:

- `2020-01-01`: strong bull-cycle expansion after a cheap regime
- `2021-01-01`: already much richer entry point
- `2022-01-01`: harsh bear-market / post-peak environment
- `2023-01-01`: recovery regime

A strategy that wins from 2020 may simply be the best "stay risk-on" strategy. A strategy that wins from 2022 or 2023 may be genuinely better at redeploying from weakness.

### Why Interval Matters

Rebalance cadence changes:

- turnover
- how quickly target changes are acted on
- how aggressively a strategy responds to noise versus trend

That is why the repo now saves multiple interval sweeps instead of just weekly runs.

## What These Results Do Not Yet Tell You

They still do not tell you:

- the tax cost of distribution
- whether weekly living-expense withdrawals are sustainable
- how much slippage KyberSwap execution would create
- whether using intraday execution windows would improve results

So the correct attitude is:

- useful decision-support
- not deploy-as-is certainty

## Practical Use Of The Current Strategies

### If The Goal Is "Use DAI To DCA Back In"

The strategies to look at first are:

- `drawdown_tilt_rebalance`
- `btc_defensive_eth_aggressive`
- `narrow_cash_band_rebalance`

They are much closer to the intended behavior than the original broad cash-band version.

### If The Goal Is "Own Both BTC And ETH Roughly Half/Half"

The natural baseline is:

- `static_50_50_rebalance`

Then compare whether tactical strategies beat it without exploding turnover or drawdown.

### If The Goal Is "Eventually Withdraw Cash"

The next business-logic milestone is:

- model explicit DAI withdrawals over time
- compare whether strategies maintain portfolio resilience under those withdrawals

The engine already supports withdrawal mechanics; the strategy research around that is the next layer rather than a missing plumbing feature.

## Recommended Next Business Questions

1. Add explicit periodic `DAI` withdrawals to the portfolio experiment matrix.
2. Define acceptable turnover and drawdown budgets, not just maximize ending value.
3. Decide whether the target long-run posture is:
   - roughly `50/50 BTC/ETH` plus elastic DAI
   - or BTC-heavy with opportunistic ETH overlays
4. Add a "current holdings -> suggested rebalance trades" layer for practical execution support.

## Bottom Line

The business logic in this repo is now organized around three distinct questions:

- what do I hold now?
- what would recurring buy rules have done historically?
- how should a BTC/ETH/DAI portfolio behave across bull and bear regimes?

Keeping those questions separate is the most important design decision in the repo.
