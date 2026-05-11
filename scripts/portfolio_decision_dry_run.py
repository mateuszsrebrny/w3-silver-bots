#!/usr/bin/env python3

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtesting.portfolio_engine import PortfolioManagementBacktestEngine, PortfolioManagementState
from scripts.run_portfolio_backtest import build_bundle, build_portfolio_strategies


UTC = timezone.utc
DEFAULT_DATA_ROOT = Path("data/market/coinbase")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Dry-run portfolio strategy decisions for one assumed BTC/ETH/DAI snapshot."
    )
    parser.add_argument("--date", required=True, help="Requested snapshot date in YYYY-MM-DD.")
    parser.add_argument("--dai", default="10000", help="Assumed DAI holdings.")
    parser.add_argument("--btc", default="0", help="Assumed BTC holdings.")
    parser.add_argument("--eth", default="0", help="Assumed ETH holdings.")
    parser.add_argument("--max-buy-trade-dai", help="Optional per-buy cap in DAI.")
    parser.add_argument("--max-buy-step-dai", help="Optional total buy budget cap per decision step in DAI.")
    parser.add_argument("--max-sell-step-dai", help="Optional total sell budget cap per decision step in DAI.")
    parser.add_argument("--reserve-dai", help="Optional soft reserve threshold in DAI for reserve-aware buying.")
    parser.add_argument("--reserve-buy-scale", default="0.50", help="Buy-budget scale used inside the reserve zone.")
    parser.add_argument("--reserve-deep-buy-scale", default="0.25", help="Buy-budget scale used deep inside the reserve zone.")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    return parser.parse_args()


def parse_date(value):
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def find_effective_timestamp(bundle, requested_timestamp):
    timestamps = bundle.common_timestamps_since(datetime(1970, 1, 1, tzinfo=UTC))
    effective = None
    for timestamp in timestamps:
        if timestamp <= requested_timestamp:
            effective = timestamp
        else:
            break
    if effective is None:
        raise ValueError("Requested date is earlier than the available market data.")
    return effective


def _pct(value):
    return f"{(value * Decimal('100')):.2f}%"


def _fmt_decimal(value, places=2):
    return f"{Decimal(value):.{places}f}"


def _signed_trade_notional(snapshot, symbol):
    total = Decimal("0")
    for trade in snapshot.trades:
        if trade.symbol != symbol:
            continue
        signed = trade.notional_usd if trade.side == "buy" else -trade.notional_usd
        total += signed
    return total


def dry_run(
    bundle,
    timestamp,
    dai_units,
    btc_units,
    eth_units,
    max_buy_trade_dai=None,
    max_buy_step_dai=None,
    max_sell_step_dai=None,
    reserve_dai=None,
    reserve_buy_scale="0.50",
    reserve_deep_buy_scale="0.25",
):
    results = []
    for strategy in build_portfolio_strategies():
        state = PortfolioManagementState(
            dai_units=Decimal(str(dai_units)),
            positions={
                "BTC-USD": Decimal(str(btc_units)),
                "ETH-USD": Decimal(str(eth_units)),
            },
        )
        engine = PortfolioManagementBacktestEngine(
            interval_days=7,
            max_buy_trade_dai=max_buy_trade_dai,
            max_buy_step_dai=max_buy_step_dai,
            max_sell_step_dai=max_sell_step_dai,
            reserve_dai=reserve_dai,
            reserve_buy_scale=reserve_buy_scale,
            reserve_deep_buy_scale=reserve_deep_buy_scale,
        )
        snapshot = engine.evaluate_step(bundle, strategy, timestamp, state)
        results.append((strategy, snapshot))
    return results


def format_report(
    bundle,
    requested_timestamp,
    effective_timestamp,
    dai_units,
    btc_units,
    eth_units,
    results,
    max_buy_trade_dai=None,
    max_buy_step_dai=None,
    max_sell_step_dai=None,
    reserve_dai=None,
):
    lines = [
        f"Requested date: {requested_timestamp.date().isoformat()}",
        f"Effective date: {effective_timestamp.date().isoformat()}",
        f"Assumed holdings: DAI={dai_units} BTC={btc_units} ETH={eth_units}",
        f"Max buy per trade: {max_buy_trade_dai if max_buy_trade_dai is not None else 'uncapped'}",
        f"Max buy per step: {max_buy_step_dai if max_buy_step_dai is not None else 'uncapped'}",
        f"Max sell per step: {max_sell_step_dai if max_sell_step_dai is not None else 'uncapped'}",
        f"Reserve DAI threshold: {reserve_dai if reserve_dai is not None else 'disabled'}",
        f"Prices: BTC={bundle.close('BTC-USD', effective_timestamp):.2f} USD, ETH={bundle.close('ETH-USD', effective_timestamp):.2f} USD",
        "",
        "strategy | reason | action | btc_trade_usd | eth_trade_usd | current_weights | target_weights | ending_holdings",
        "--- | --- | --- | ---: | ---: | --- | --- | ---",
    ]

    for strategy, snapshot in results:
        btc_trade = _signed_trade_notional(snapshot, "BTC-USD")
        eth_trade = _signed_trade_notional(snapshot, "ETH-USD")
        current_weights = (
            f"BTC {_pct(snapshot.current_weights['BTC-USD'])}, "
            f"ETH {_pct(snapshot.current_weights['ETH-USD'])}, "
            f"DAI {_pct(snapshot.current_weights['DAI'])}"
        )
        target_weights = (
            f"BTC {_pct(snapshot.target_weights['BTC-USD'])}, "
            f"ETH {_pct(snapshot.target_weights['ETH-USD'])}, "
            f"DAI {_pct(snapshot.target_weights['DAI'])}"
        )
        ending_holdings = (
            f"DAI {_fmt_decimal(snapshot.allocation_point.dai_units, 2)}, "
            f"BTC {_fmt_decimal(snapshot.allocation_point.btc_units, 6)}, "
            f"ETH {_fmt_decimal(snapshot.allocation_point.eth_units, 6)}"
        )
        lines.append(
            f"{strategy.name} | "
            f"{snapshot.decision.reason} | "
            f"{snapshot.allocation_point.action} | "
            f"{_fmt_decimal(btc_trade, 2)} | "
            f"{_fmt_decimal(eth_trade, 2)} | "
            f"{current_weights} | "
            f"{target_weights} | "
            f"{ending_holdings}"
        )

    return "\n".join(lines)


def main():
    args = parse_args()
    requested_timestamp = parse_date(args.date)
    bundle = build_bundle(args.data_root)
    effective_timestamp = find_effective_timestamp(bundle, requested_timestamp)
    results = dry_run(
        bundle=bundle,
        timestamp=effective_timestamp,
        dai_units=args.dai,
        btc_units=args.btc,
        eth_units=args.eth,
        max_buy_trade_dai=args.max_buy_trade_dai,
        max_buy_step_dai=args.max_buy_step_dai,
        max_sell_step_dai=args.max_sell_step_dai,
        reserve_dai=args.reserve_dai,
        reserve_buy_scale=args.reserve_buy_scale,
        reserve_deep_buy_scale=args.reserve_deep_buy_scale,
    )
    print(
        format_report(
            bundle=bundle,
            requested_timestamp=requested_timestamp,
            effective_timestamp=effective_timestamp,
            dai_units=args.dai,
            btc_units=args.btc,
            eth_units=args.eth,
            results=results,
            max_buy_trade_dai=args.max_buy_trade_dai,
            max_buy_step_dai=args.max_buy_step_dai,
            max_sell_step_dai=args.max_sell_step_dai,
            reserve_dai=args.reserve_dai,
        )
    )


if __name__ == "__main__":
    main()
