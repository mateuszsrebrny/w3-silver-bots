#!/usr/bin/env python3

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.portfolio_decision_dry_run import (
    DEFAULT_DATA_ROOT,
    _fmt_decimal,
    _pct,
    _signed_trade_notional,
    dry_run,
    find_effective_timestamp,
    parse_date,
)
from scripts.run_portfolio_backtest import build_bundle
from backtesting.portfolio_strategies import _asset_signal


UTC = timezone.utc
DEFAULT_STRATEGY = "budgeted_btc_defensive_eth_aggressive"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Print a concise Sunday recommendation for one portfolio strategy."
    )
    parser.add_argument("--date", default=datetime.now(tz=UTC).date().isoformat())
    parser.add_argument("--dai", default="10000")
    parser.add_argument("--btc", default="0")
    parser.add_argument("--eth", default="0")
    parser.add_argument("--strategy", default=DEFAULT_STRATEGY)
    parser.add_argument("--max-buy-trade-dai")
    parser.add_argument("--max-buy-step-dai", default="500")
    parser.add_argument("--max-sell-step-dai")
    parser.add_argument("--reserve-dai", default="2500")
    parser.add_argument("--reserve-buy-scale", default="0.50")
    parser.add_argument("--reserve-deep-buy-scale", default="0.25")
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    return parser.parse_args()


def _current_values(bundle, timestamp, btc_units, eth_units, dai_units):
    btc_value = Decimal(str(btc_units)) * bundle.close("BTC-USD", timestamp)
    eth_value = Decimal(str(eth_units)) * bundle.close("ETH-USD", timestamp)
    dai_value = Decimal(str(dai_units))
    total = btc_value + eth_value + dai_value
    return {
        "BTC-USD": btc_value,
        "ETH-USD": eth_value,
        "DAI": dai_value,
        "TOTAL": total,
    }


def _find_strategy_snapshot(results, strategy_name):
    for strategy, snapshot in results:
        if strategy.name == strategy_name:
            return strategy, snapshot
    raise ValueError(f"Unknown strategy: {strategy_name}")


def _strategy_diagnostics(bundle, timestamp, strategy):
    diagnostics = {
        "btc": _asset_signal(bundle, "BTC-USD", timestamp, 200, 365),
        "eth": _asset_signal(bundle, "ETH-USD", timestamp, 200, 365),
        "btc_return_84d": bundle.trailing_return("BTC-USD", timestamp, 84),
        "eth_return_84d": bundle.trailing_return("ETH-USD", timestamp, 84),
        "notes": [],
    }

    btc = diagnostics["btc"]
    eth = diagnostics["eth"]
    btc_return = diagnostics["btc_return_84d"]
    eth_return = diagnostics["eth_return_84d"]

    if btc is None or eth is None:
        diagnostics["notes"].append("Market diagnostics unavailable for this date.")
        return diagnostics

    if strategy.name == "budgeted_btc_defensive_eth_aggressive":
        if btc["cheap"] and eth["cheap"]:
            diagnostics["notes"].append(
                "Both BTC and ETH are still in the strategy's cheap/weak bucket."
            )
            if eth_return is not None and btc_return is not None:
                diagnostics["notes"].append(
                    "ETH has not cleared the relative-strength filter versus BTC, so the buy stays BTC-heavy."
                )
        elif eth_return is not None and btc_return is not None and eth_return > btc_return:
            diagnostics["notes"].append(
                "ETH is beating BTC on 84-day return while no longer looking cheap, so the strategy treats this as risk-on."
            )
        else:
            diagnostics["notes"].append(
                "BTC looks stronger on the trend/discount test, so the strategy stays defensive."
            )
    elif strategy.name == "budgeted_drawdown_tilt_rebalance":
        if btc["drawdown"] > eth["drawdown"]:
            diagnostics["notes"].append(
                "BTC is further below its 365-day high, so the drawdown tilt favors BTC."
            )
        elif eth["drawdown"] > btc["drawdown"]:
            diagnostics["notes"].append(
                "ETH is further below its 365-day high, so the drawdown tilt favors ETH."
            )
        else:
            diagnostics["notes"].append(
                "BTC and ETH have similar drawdowns, so the strategy stays close to balanced."
            )
    elif strategy.name == "budgeted_static_50_50_rebalance":
        diagnostics["notes"].append(
            "This strategy ignores market regime and just moves the portfolio toward its fixed target."
        )

    return diagnostics


def format_recommendation(
    bundle,
    requested_timestamp,
    effective_timestamp,
    strategy,
    snapshot,
    dai_units,
    btc_units,
    eth_units,
    max_buy_step_dai,
    reserve_dai,
):
    btc_trade = _signed_trade_notional(snapshot, "BTC-USD")
    eth_trade = _signed_trade_notional(snapshot, "ETH-USD")
    current_values = _current_values(bundle, effective_timestamp, btc_units, eth_units, dai_units)
    diagnostics = _strategy_diagnostics(bundle, effective_timestamp, strategy)
    btc_signal = diagnostics["btc"]
    eth_signal = diagnostics["eth"]
    btc_return = diagnostics["btc_return_84d"]
    eth_return = diagnostics["eth_return_84d"]

    lines = [
        f"Requested date: {requested_timestamp.date().isoformat()}",
        f"Effective date: {effective_timestamp.date().isoformat()}",
        f"Strategy: {strategy.name}",
        f"Reason: {snapshot.decision.reason}",
        f"Action: {snapshot.allocation_point.action}",
        "",
        "Current portfolio:",
        f"- DAI: {_fmt_decimal(dai_units, 2)}",
        f"- BTC: {_fmt_decimal(btc_units, 6)} ({_fmt_decimal(current_values['BTC-USD'], 2)} USD)",
        f"- ETH: {_fmt_decimal(eth_units, 6)} ({_fmt_decimal(current_values['ETH-USD'], 2)} USD)",
        f"- Total: {_fmt_decimal(current_values['TOTAL'], 2)} USD",
        "",
        "Current weights:",
        f"- BTC: {_pct(snapshot.current_weights['BTC-USD'])}",
        f"- ETH: {_pct(snapshot.current_weights['ETH-USD'])}",
        f"- DAI: {_pct(snapshot.current_weights['DAI'])}",
        "",
        "Target weights:",
        f"- BTC: {_pct(snapshot.target_weights['BTC-USD'])}",
        f"- ETH: {_pct(snapshot.target_weights['ETH-USD'])}",
        f"- DAI: {_pct(snapshot.target_weights['DAI'])}",
        "",
        "Trade recommendation:",
        f"- BTC: {_fmt_decimal(btc_trade, 2)} USD",
        f"- ETH: {_fmt_decimal(eth_trade, 2)} USD",
        "",
        "Risk controls:",
        f"- Max buy per step: {max_buy_step_dai if max_buy_step_dai is not None else 'uncapped'}",
        f"- Reserve DAI threshold: {reserve_dai if reserve_dai is not None else 'disabled'}",
    ]

    if btc_signal is not None and eth_signal is not None:
        lines.extend(
            [
                "",
                "Signal diagnostics:",
                (
                    f"- BTC: close {_fmt_decimal(btc_signal['close'], 2)} vs MA200 {_fmt_decimal(btc_signal['moving_average'], 2)}, "
                    f"drawdown365 {_pct(btc_signal['drawdown'])}, cheap={str(btc_signal['cheap']).lower()}, "
                    f"expensive={str(btc_signal['expensive']).lower()}"
                ),
                (
                    f"- ETH: close {_fmt_decimal(eth_signal['close'], 2)} vs MA200 {_fmt_decimal(eth_signal['moving_average'], 2)}, "
                    f"drawdown365 {_pct(eth_signal['drawdown'])}, cheap={str(eth_signal['cheap']).lower()}, "
                    f"expensive={str(eth_signal['expensive']).lower()}"
                ),
            ]
        )
        if btc_return is not None and eth_return is not None:
            lines.extend(
                [
                    (
                        f"- Relative returns (84d): BTC {_pct(btc_return)}, ETH {_pct(eth_return)}"
                    )
                ]
            )

    if diagnostics["notes"]:
        lines.extend(
            [
                "",
                "Why this strategy thinks that:",
                *[f"- {note}" for note in diagnostics["notes"]],
            ]
        )

    lines.extend(
        [
        "",
        "Post-trade holdings:",
        f"- DAI: {_fmt_decimal(snapshot.allocation_point.dai_units, 2)}",
        f"- BTC: {_fmt_decimal(snapshot.allocation_point.btc_units, 6)}",
        f"- ETH: {_fmt_decimal(snapshot.allocation_point.eth_units, 6)}",
    ]
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
    strategy, snapshot = _find_strategy_snapshot(results, args.strategy)
    print(
        format_recommendation(
            bundle=bundle,
            requested_timestamp=requested_timestamp,
            effective_timestamp=effective_timestamp,
            strategy=strategy,
            snapshot=snapshot,
            dai_units=args.dai,
            btc_units=args.btc,
            eth_units=args.eth,
            max_buy_step_dai=args.max_buy_step_dai,
            reserve_dai=args.reserve_dai,
        )
    )


if __name__ == "__main__":
    main()
