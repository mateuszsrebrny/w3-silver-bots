# w3-silver-bots

This repository currently contains three related tools:

- a multichain portfolio tracker for on-chain balances and live valuation
- a historical market-data sync layer for BTC and ETH daily candles
- a backtesting framework for DCA and BTC/ETH/DAI portfolio-management strategies

It started as an older Web3 tracking script and has been refactored into a small research/workflow repo.

## What Is Where

- [portfolio_tracker.py](/home/mati/devel/w3-silver-bots/portfolio_tracker.py:1)
  - CLI for the live portfolio tracker
  - loads wallet from `.env`
  - scans configured chains and tracked tokens
  - values holdings in `USDC` using KyberSwap quotes

- [botweb3lib.py](/home/mati/devel/w3-silver-bots/botweb3lib.py:1)
  - generic blockchain access layer
  - loads `chains.config.yaml`
  - fetches native/ERC-20 balances
  - asks KyberSwap for live route-based prices

- [chains.config.yaml](/home/mati/devel/w3-silver-bots/chains.config.yaml:1)
  - chain RPC URLs
  - token addresses
  - token decimal metadata

- [market_data](/home/mati/devel/w3-silver-bots/market_data:1)
  - historical candle model, provider, CSV store, sync service
  - used for offline backtests, not for live execution quotes

- [scripts/sync_market_data.py](/home/mati/devel/w3-silver-bots/scripts/sync_market_data.py:1)
  - seeds and updates daily BTC/ETH candle history

- [backtesting](/home/mati/devel/w3-silver-bots/backtesting:1)
  - reusable series, engines, strategies, and reporting
  - contains both DCA-style and portfolio-management backtests

- [scripts/run_backtest.py](/home/mati/devel/w3-silver-bots/scripts/run_backtest.py:1)
  - runs recurring-contribution DCA experiments

- [scripts/run_portfolio_backtest.py](/home/mati/devel/w3-silver-bots/scripts/run_portfolio_backtest.py:1)
  - runs initial-portfolio BTC/ETH/DAI management experiments
  - saves CSV/Markdown/text summaries and wallet-value SVG charts

- [scripts/plot_backtest_scatter.py](/home/mati/devel/w3-silver-bots/scripts/plot_backtest_scatter.py:1)
  - generates scatter plots from saved DCA backtest CSV output

- [reports/backtests](/home/mati/devel/w3-silver-bots/reports/backtests:1)
  - saved recurring-DCA experiment outputs

- [reports/portfolio_backtests](/home/mati/devel/w3-silver-bots/reports/portfolio_backtests:1)
  - saved portfolio-management experiment outputs

- [tests](/home/mati/devel/w3-silver-bots/tests:1)
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

Tracked tokens are defined in [portfolio_tracker.py](/home/mati/devel/w3-silver-bots/portfolio_tracker.py:1), while chain/token metadata comes from [chains.config.yaml](/home/mati/devel/w3-silver-bots/chains.config.yaml:1).

## Syncing Historical Data

Seed or update local daily candles:

```bash
.venv/bin/python scripts/sync_market_data.py --product BTC-USD --product ETH-USD --since 2020-01-01
```

This writes local CSVs under [data/market/coinbase](/home/mati/devel/w3-silver-bots/data/market/coinbase:1).

## Running Recurring DCA Backtests

```bash
.venv/bin/python scripts/run_backtest.py
```

This runs:

- single-asset BTC or ETH recurring-buy strategies
- dual-asset BTC/ETH allocation strategies
- multiple start dates and cadences

Outputs go under [reports/backtests](/home/mati/devel/w3-silver-bots/reports/backtests:1).

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

Outputs go under [reports/portfolio_backtests](/home/mati/devel/w3-silver-bots/reports/portfolio_backtests:1) and include:

- CSV summaries
- Markdown summaries
- text tables
- manifest metadata
- SVG wallet-value charts per `(start date, interval)` scenario

## Tests

Run the full suite:

```bash
.venv/bin/pytest
```

CI is configured in GitHub Actions and runs the test suite on pushes and pull requests.

## Documentation

- [TECHNICAL_DESIGN.md](/home/mati/devel/w3-silver-bots/TECHNICAL_DESIGN.md:1)
  - code structure, boundaries, data flow, and test design

- [BUSINESS_LOGIC.md](/home/mati/devel/w3-silver-bots/BUSINESS_LOGIC.md:1)
  - strategy intent, assumptions, limitations, and interpretation guidance

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
