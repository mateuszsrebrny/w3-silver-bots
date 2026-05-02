# Technical Design

## Purpose

This repo has three technical subsystems:

1. live multichain portfolio tracking
2. historical market-data collection
3. backtesting and experiment reporting

They share some domain concepts, but they are intentionally separated so live wallet tooling does not become entangled with historical research code.

## High-Level Architecture

### 1. Live Tracker

Files:

- [portfolio_tracker.py](/home/mati/devel/w3-silver-bots/portfolio_tracker.py:1)
- [botweb3lib.py](/home/mati/devel/w3-silver-bots/botweb3lib.py:1)
- [chains.config.yaml](/home/mati/devel/w3-silver-bots/chains.config.yaml:1)

Responsibilities:

- `portfolio_tracker.py`
  - portfolio-specific policy
  - defines which chains to scan
  - defines which tokens are relevant on each chain
  - turns generic balance/quote calls into printable portfolio rows

- `botweb3lib.py`
  - generic chain access
  - RPC connection management
  - token metadata lookup
  - native/ERC-20 balance reads
  - KyberSwap quote requests

- `chains.config.yaml`
  - declarative network and token metadata
  - no strategy logic

Design boundary:

- `botweb3lib.py` should remain generic infrastructure
- `portfolio_tracker.py` should remain the opinionated "what do we care about?" layer

### 2. Historical Market Data

Files:

- [market_data/candles.py](/home/mati/devel/w3-silver-bots/market_data/candles.py:1)
- [market_data/providers.py](/home/mati/devel/w3-silver-bots/market_data/providers.py:1)
- [market_data/store.py](/home/mati/devel/w3-silver-bots/market_data/store.py:1)
- [market_data/sync.py](/home/mati/devel/w3-silver-bots/market_data/sync.py:1)
- [scripts/sync_market_data.py](/home/mati/devel/w3-silver-bots/scripts/sync_market_data.py:1)

Responsibilities:

- `candles.py`
  - canonical candle model
  - UTC/time-granularity helpers

- `providers.py`
  - remote API fetching
  - currently Coinbase daily candles

- `store.py`
  - CSV persistence
  - merge, dedupe, validation, gap detection

- `sync.py`
  - orchestration layer
  - `seed`, `update`, `repair`, `sync`

- `sync_market_data.py`
  - user-facing CLI

Design goals:

- local, reproducible datasets
- deterministic backtest inputs
- validation before strategy research

### 3. Backtesting

Files:

- [backtesting/series.py](/home/mati/devel/w3-silver-bots/backtesting/series.py:1)
- [backtesting/multi_asset.py](/home/mati/devel/w3-silver-bots/backtesting/multi_asset.py:1)
- [backtesting/engine.py](/home/mati/devel/w3-silver-bots/backtesting/engine.py:1)
- [backtesting/rotation_engine.py](/home/mati/devel/w3-silver-bots/backtesting/rotation_engine.py:1)
- [backtesting/portfolio_engine.py](/home/mati/devel/w3-silver-bots/backtesting/portfolio_engine.py:1)
- [backtesting/strategies.py](/home/mati/devel/w3-silver-bots/backtesting/strategies.py:1)
- [backtesting/rotation_strategies.py](/home/mati/devel/w3-silver-bots/backtesting/rotation_strategies.py:1)
- [backtesting/portfolio_strategies.py](/home/mati/devel/w3-silver-bots/backtesting/portfolio_strategies.py:1)
- [backtesting/reporting.py](/home/mati/devel/w3-silver-bots/backtesting/reporting.py:1)
- [scripts/run_backtest.py](/home/mati/devel/w3-silver-bots/scripts/run_backtest.py:1)
- [scripts/run_portfolio_backtest.py](/home/mati/devel/w3-silver-bots/scripts/run_portfolio_backtest.py:1)
- [scripts/plot_backtest_scatter.py](/home/mati/devel/w3-silver-bots/scripts/plot_backtest_scatter.py:1)

The backtesting layer has three engines because the state machines are different:

- `BacktestEngine`
  - recurring contributions into one asset

- `RotationBacktestEngine`
  - recurring contributions split between BTC and ETH

- `PortfolioManagementBacktestEngine`
  - no recurring contributions by default
  - starts from an initial portfolio
  - supports buys, sells, rebalancing, and optional DAI withdrawals

## Core Data Models

### Price Series

`PriceSeries` in [backtesting/series.py](/home/mati/devel/w3-silver-bots/backtesting/series.py:1):

- loads validated CSV candles
- provides:
  - `close_at`
  - trailing moving average
  - trailing return
  - drawdown from rolling high

`MultiAssetSeries` in [backtesting/multi_asset.py](/home/mati/devel/w3-silver-bots/backtesting/multi_asset.py:1):

- wraps multiple `PriceSeries`
- provides common timestamps across symbols
- exposes multi-asset indicator queries

This keeps indicators deterministic and local.

### Results

There are two result families:

- `BacktestResult`
  - recurring-contribution DCA and BTC/ETH rotation experiments

- `PortfolioBacktestResult`
  - BTC/ETH/DAI management experiments

This split exists because portfolio-management results need different accounting:

- `gross_buys_dai`
- `gross_sells_dai`
- `net_buys_dai`
- `ending_dai`
- `ending_btc_units`
- `ending_eth_units`
- `realized_value`
- `turnover_pct`

Reusing DCA metrics like `deployment_pct` for rebalancing strategies was explicitly removed because it produced misleading summaries.

## Strategy Interfaces

### Single-Asset DCA

`Decision` in [backtesting/strategies.py](/home/mati/devel/w3-silver-bots/backtesting/strategies.py:1):

- `buy_usd`
- `reason`

Used by:

- `WeeklyFixedDCA`
- `WeeklyMATrendDCA`
- `WeeklyDipDCA`
- `WeeklyMAScaledDCA`
- `WeeklyDrawdownScaledDCA`

### Dual-Asset Recurring Allocation

`AllocationDecision` in [backtesting/rotation_strategies.py](/home/mati/devel/w3-silver-bots/backtesting/rotation_strategies.py:1):

- `weights`
- `reason`

Used by:

- BTC-only / ETH-only / equal-split baselines
- momentum strategies
- contrarian MA strategies
- BTC-core/ETH-overlay strategy

### Portfolio Management

`TargetAllocationDecision` in [backtesting/portfolio_strategies.py](/home/mati/devel/w3-silver-bots/backtesting/portfolio_strategies.py:1):

- `target_weights`
- `rebalance_fraction`
- `reason`

This is a different abstraction because the engine is moving an existing portfolio toward a target state rather than deciding where one new contribution goes.

## Strategy Families Implemented

### Recurring Single-Asset DCA

- fixed DCA
- buy only above MA
- buy only below MA
- buy more when below MA
- buy more on drawdowns

### Recurring BTC/ETH Allocation

- BTC-only
- ETH-only
- equal split
- stronger-return momentum
- weaker-return mean reversion
- BTC/ETH MA-based contrarian selectors
- BTC core with conditional ETH overlay

### BTC/ETH/DAI Portfolio Management

- static 50/50 rebalance with cash bucket
- broad cash-band rebalance
- narrow cash-band rebalance
- drawdown-tilted rebalance
- BTC-defensive / ETH-aggressive regime strategy

## Reporting And Artifacts

### DCA/Rotation Outputs

Saved under [reports/backtests](/home/mati/devel/w3-silver-bots/reports/backtests:1):

- CSV
- Markdown
- text table
- manifest
- scatter SVGs

### Portfolio Outputs

Saved under [reports/portfolio_backtests](/home/mati/devel/w3-silver-bots/reports/portfolio_backtests:1):

- CSV
- Markdown
- text table
- manifest
- one equity-curve SVG per `(start, interval)` scenario

The `latest/` directory mirrors the most recent run for quick inspection.

## Data Flow

### Live Tracker Flow

1. load `.env`
2. load chain config
3. create `BlockchainAccess` per chain
4. fetch token balances
5. quote token -> `USDC` via KyberSwap
6. sort and print balances

### Historical Research Flow

1. sync local BTC/ETH candles from Coinbase
2. load candles into `PriceSeries`
3. run one of the backtest engines
4. serialize experiment results
5. generate plots

## Test Strategy

Tests live in [tests](/home/mati/devel/w3-silver-bots/tests:1).

Coverage intentionally includes:

- low-level balance/pricing helpers in `botweb3lib.py`
- tracker policy in `portfolio_tracker.py`
- market-data normalization, store behavior, and sync orchestration
- backtest engines and strategy decisions
- CLI/script behavior for:
  - market-data sync
  - DCA backtests
  - portfolio backtests
  - scatter plotting

Principles:

- no live network dependency in tests
- deterministic fixtures
- script-entrypoint coverage to prevent silent regression of `if __name__ == "__main__"`

## CI

GitHub Actions runs `pytest` on pushes and pull requests.

The project currently uses tests as the main regression net. There is no separate lint/type-check layer yet.

## Known Design Constraints

- historical backtests operate on daily candles only
- no tax model
- no exchange/DEX execution slippage model in backtests
- live tracker and research layer intentionally use different price sources
- `portfolio_tracker.py` tracked token list is still code-defined rather than config-driven

## Suggested Future Cleanup

- move tracked token lists from code into config if they become user-managed
- add hourly candles for execution-window research
- add optional transaction-cost assumptions in backtests
- add a richer portfolio strategy runner that can output concrete trade deltas from current holdings
