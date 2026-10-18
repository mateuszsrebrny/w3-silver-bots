# w3-silver-bots

This repository currently contains three related tools:

- a multichain portfolio tracker for on-chain balances and live valuation
- a historical market-data sync layer for BTC and ETH daily candles
- a backtesting framework for DCA and BTC/ETH/DAI portfolio-management strategies

It started as an older Web3 tracking script and has been refactored into a small research/workflow repo.

## What Is Where

- [portfolio_tracker.py](portfolio_tracker.py)
  - CLI for the live portfolio tracker
  - loads wallet from `.env`
  - scans configured chains and tracked tokens
  - values holdings in `USDC` using KyberSwap quotes

- [botweb3lib.py](botweb3lib.py)
  - generic blockchain access layer
  - loads `chains.config.yaml`
  - fetches native/ERC-20 balances
  - asks KyberSwap for live route-based prices

- [chains.config.yaml](chains.config.yaml)
  - chain RPC URLs
  - token addresses
  - token decimal metadata

- [market_data](market_data)
  - historical candle model, provider, CSV store, sync service
  - used for offline backtests, not for live execution quotes

- [scripts/sync_market_data.py](scripts/sync_market_data.py)
  - seeds and updates daily BTC/ETH candle history

- [backtesting](backtesting)
  - reusable series, engines, strategies, and reporting
  - contains both DCA-style and portfolio-management backtests

- [scripts/run_backtest.py](scripts/run_backtest.py)
  - runs recurring-contribution DCA experiments

- [scripts/run_portfolio_backtest.py](scripts/run_portfolio_backtest.py)
  - runs initial-portfolio BTC/ETH/DAI management experiments
  - saves CSV/Markdown/text summaries and wallet-value SVG charts
  - primary report artifacts now focus on the budgeted live-execution strategy family

- [scripts/portfolio_decision_dry_run.py](scripts/portfolio_decision_dry_run.py)
  - evaluates one assumed `DAI/BTC/ETH` snapshot on one date
  - prints what each portfolio strategy would buy, sell, or hold

- [scripts/sunday_recommendation.py](scripts/sunday_recommendation.py)
  - prints one concise Sunday recommendation for the chosen live strategy
  - intended as the operator-facing wrapper around the dry-run logic

- [scripts/plot_backtest_scatter.py](scripts/plot_backtest_scatter.py)
  - generates scatter plots from saved DCA backtest CSV output

- [reports/backtests](reports/backtests)
  - saved recurring-DCA experiment outputs

- [reports/portfolio_backtests](reports/portfolio_backtests)
  - saved portfolio-management experiment outputs

- [tests](tests)
  - unit and script-level tests for the tracker, market data, and backtesting layers

## Main Concepts

There are two separate pricing/data domains in this repo:

- live portfolio valuation:
  - uses on-chain balances plus `KyberSwap` route quotes
  - intended for "what is my wallet worth now?"

- historical backtesting:
  - uses local daily candle history for `BTC-USD` and `ETH-USD`
  - intended for "how would this strategy have behaved over the last few years?"

Those are intentionally separate. Historical backtests do not try to reconstruct historical DEX execution routes.

## Setup

Create a venv and install dependencies:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt
```

Create `.env` with at least:

```bash
WALLET=0xYourWalletAddress
BOT_WALLET=0xYourBotWalletAddress
BOT_PRIVATE_KEY=0xyour_bot_private_key_here
```

## Running The Tracker

```bash
.venv/bin/python portfolio_tracker.py
```

The tracker currently scans:

- `polygon`
- `optimism`
- `ethereum`
- `arbitrum`

To include a Bittensor coldkey in the same run, set `BITTENSOR_WALLET` in
`.env` (public SS58 address only) or pass `--bittensor-wallet 5YourColdkey`.
Use `--chain bittensor` to query only Bittensor. The tracker reads free TAO and
staked TAO/alpha across subnets. Alpha is valued at on-chain TAO/alpha spot,
then all Bittensor positions are converted with Coinbase's TAO/USD spot price.
The displayed USDC equivalent assumes USD and USDC parity; it is not an
executable exit quote and excludes unstaking slippage and fees. No Bittensor
private key or mnemonic is needed.

Tracked tokens are defined in [portfolio_tracker.py](portfolio_tracker.py), while chain/token metadata comes from [chains.config.yaml](chains.config.yaml).

## Syncing Historical Data

Seed or update local daily candles:

```bash
.venv/bin/python scripts/sync_market_data.py --product BTC-USD --product ETH-USD --since 2020-01-01
```

This writes local CSVs under [data/market/coinbase](data/market/coinbase).

### Historical dTAO snapshots

The read-only dTAO sync uses the Bittensor archive node. Bittensor and Web3
share the project's `.venv` (Web3 7.16 supports Bittensor's `websockets`
requirement).

```bash
.venv/bin/python scripts/sync_dtao_history.py --network wss://archive.sub.latent.to:443 --since 2025-02-14 --until 2025-02-20 --resume
```

Without dates, the script snapshots today at the first finalized block at or
after 00:30 UTC; run it after that time. It writes `data/dtao/daily.csv`, which
is local and gitignored. Re-running a day replaces that day's rows. Each row
contains the block, subnet number, registration block, TAO/alpha pool reserves
and implied TAO-per-alpha spot price. The registration block distinguishes
reused subnet numbers and avoids mixing different incarnations in a backtest.
This is a daily price snapshot, not OHLC or realized staking return.
`--resume` skips dates already in the CSV after an interrupted backfill; omit it
when you want to refresh a previously saved date.
Archive endpoints can rate-limit historical reads; the alternate endpoint above
completed the initial backfill, while the default endpoint refused old blocks.

### Price-only dTAO basket backtest

```bash
.venv/bin/python scripts/run_dtao_backtest.py --netuids 4,9,44 --target-tao 1 --trim-trigger-tao 1.2
```

The script starts at the first date shared by the **current incarnation** of
each selected subnet, invests one TAO per subnet at that day's spot price,
and compares holding with a weekly Sunday rule: when an alpha position is
worth more than 1.2 TAO, sell it down to 1 TAO and retain the proceeds as
free TAO. It reports final portfolio values, trim count and daily max drawdown.
It refuses missing daily prices rather than forward-filling them.

This is a price-only comparison in TAO, not a staking-performance simulation.
It excludes alpha dividends, swap impact, fees and validator differences.
Choosing today's subnets for a historical test also introduces selection bias;
the result cannot establish how a historical top-11 selection rule would fare.

## Running Recurring DCA Backtests

```bash
.venv/bin/python scripts/run_backtest.py
```

This runs:

- single-asset BTC or ETH recurring-buy strategies
- dual-asset BTC/ETH allocation strategies
- multiple start dates and cadences

Outputs go under [reports/backtests](reports/backtests).

## Running Portfolio-Management Backtests

```bash
.venv/bin/python scripts/run_portfolio_backtest.py
```

This runs strategies that start from an initial:

- `BTC` holding
- `ETH` holding
- `DAI` cash reserve

and then buy/sell/rebalance over time.

Default start portfolio is:

- `0.5 BTC`
- `5 ETH`
- `10000 DAI`

Outputs go under [reports/portfolio_backtests](reports/portfolio_backtests) and include:

- CSV summaries
- Markdown summaries
- text tables
- manifest metadata
- SVG wallet-value charts per `(start date, interval)` scenario
- weekly `allocation/trade charts`
- strategy catalog and negative-window summaries for denser portfolio sweeps

Useful flags:

```bash
.venv/bin/python scripts/run_portfolio_backtest.py --interval-days 7 --max-buy-step-dai 500
.venv/bin/python scripts/run_portfolio_backtest.py --interval-days 7 --max-buy-step-dai 100 --quarterly-starts --quarterly-starts-from 2020-01-01
.venv/bin/python scripts/run_portfolio_backtest.py --interval-days 7 --max-buy-step-dai 500 --quarterly-starts --quarterly-starts-from 2020-01-01
```

These are useful when you want to limit total weekly buy deployment and compare strategies across denser starting points.

For a one-date decision dry-run with assumed holdings:

```bash
.venv/bin/python scripts/portfolio_decision_dry_run.py --date 2026-05-04 --dai 10000 --btc 0 --eth 0 --max-buy-step-dai 100
```

This is useful when you want to ask "what would each strategy do on this date?" without rerunning the whole backtest matrix.

For a concise operator-facing recommendation:

```bash
.venv/bin/python scripts/sunday_recommendation.py --date 2026-05-10 --dai 10000 --btc 0.07 --eth 3
```

## Tests

Run the full suite:

```bash
.venv/bin/pytest
```

CI is configured in GitHub Actions and runs the test suite on pushes and pull requests.

## Documentation

- [TECHNICAL_DESIGN.md](TECHNICAL_DESIGN.md)
  - code structure, boundaries, data flow, and test design

- [BUSINESS_LOGIC.md](BUSINESS_LOGIC.md)
  - strategy intent, assumptions, limitations, and interpretation guidance

- [reports/portfolio_backtests/latest/README.md](reports/portfolio_backtests/latest/README.md)
  - how to read the current portfolio-backtest report set
  - explains the files, chart types, and cap-specific folders

## Current Scope And Limits

- Live valuation depends on:
  - working public RPC endpoints
  - KyberSwap route availability

- Historical backtests currently use:
  - daily candles only
  - no taxes
  - no realistic execution slippage model
  - simplified portfolio accounting for rebalancing and withdrawals

- `aDAI` is intentionally simplified away in portfolio-management backtests:
  - portfolio cash is modeled as plain `DAI`

- Some old ABI files remain in `abi/`, but the active valuation path is now KyberSwap-based rather than bespoke DEX integrations.
