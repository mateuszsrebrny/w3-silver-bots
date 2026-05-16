#!/usr/bin/env python3

import argparse
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtesting.lp_comparison import LPComparisonBacktestEngine
from backtesting.multi_asset import MultiAssetSeries
from backtesting.reporting import (
    format_results_markdown,
    format_results_table,
    write_manifest_json,
    write_results_csv,
)
from backtesting.series import PriceSeries
from market_data.candles import Candle


UTC = timezone.utc
DEFAULT_DATA_ROOT = Path("data/market/coinbase")
DEFAULT_OUTPUT_DIR = Path("reports/lp_backtests")
DEFAULT_SINCE_DATES = ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"]
PAIR_CONFIGS = {
    "wbtc-weth": {
        "symbols": ("BTC-USD", "ETH-USD"),
        "default_yield_pct": "26",
    },
    "usdt-weth": {
        "symbols": ("USDT-USD", "ETH-USD"),
        "default_yield_pct": "45",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(description="Compare WETH holding vs 50/50 hold vs LP exposure.")
    parser.add_argument("--since", action="append", help="Repeat to evaluate multiple start dates in YYYY-MM-DD.")
    parser.add_argument(
        "--pair",
        action="append",
        choices=sorted(PAIR_CONFIGS.keys()),
        help="Repeat to evaluate multiple LP pairs.",
    )
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--initial-value", default="10000")
    parser.add_argument("--yield-mode", choices=["apr", "apy"], default="apr")
    parser.add_argument("--wbtc-weth-yield-pct", default=PAIR_CONFIGS["wbtc-weth"]["default_yield_pct"])
    parser.add_argument("--usdt-weth-yield-pct", default=PAIR_CONFIGS["usdt-weth"]["default_yield_pct"])
    return parser.parse_args()


def parse_since(value):
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def build_constant_series_from_template(template_series, product_id, close="1"):
    close = Decimal(str(close))
    candles = [
        Candle(
            timestamp=candle.timestamp,
            open=close,
            high=close,
            low=close,
            close=close,
            volume="0",
            source="synthetic",
            product_id=product_id,
            granularity=template_series.granularity,
        )
        for candle in template_series.candles()
    ]
    return PriceSeries(product_id, template_series.granularity, candles)


def build_bundle(pair_name, data_root):
    root = Path(data_root)
    eth_series = PriceSeries.from_csv(root / "ETH-USD-1d.csv")
    if pair_name == "wbtc-weth":
        btc_series = PriceSeries.from_csv(root / "BTC-USD-1d.csv")
        return MultiAssetSeries({"BTC-USD": btc_series, "ETH-USD": eth_series})
    if pair_name == "usdt-weth":
        usdt_series = build_constant_series_from_template(eth_series, "USDT-USD", close="1")
        return MultiAssetSeries({"USDT-USD": usdt_series, "ETH-USD": eth_series})
    raise ValueError(f"Unsupported pair: {pair_name}")


def run_lp_comparison_matrix(pairs, since_dates, initial_value, yield_mode, data_root, pair_yields):
    results = []
    for pair_name in pairs:
        bundle = build_bundle(pair_name, data_root)
        config = PAIR_CONFIGS[pair_name]
        engine = LPComparisonBacktestEngine(
            fee_yield_pct=pair_yields[pair_name],
            yield_mode=yield_mode,
        )
        for since in since_dates:
            results.extend(
                engine.run_pair(
                    bundle=bundle,
                    pair_name=pair_name,
                    since=since,
                    initial_value=initial_value,
                )
            )
    return results


def build_manifest(args, since_dates, pairs):
    return {
        "generated_at_utc": datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "since_dates": [date.date().isoformat() for date in since_dates],
        "pairs": pairs,
        "initial_value": str(args.initial_value),
        "yield_mode": args.yield_mode,
        "pair_yields_pct": {
            "wbtc-weth": str(args.wbtc_weth_yield_pct),
            "usdt-weth": str(args.usdt_weth_yield_pct),
        },
        "data_root": str(args.data_root),
    }


def build_run_id(now=None):
    now = now or datetime.now(tz=UTC)
    return now.strftime("%Y%m%d-%H%M%S")


def break_even_apr_pct(lp_result, benchmark_result):
    lp_final = Decimal(str(lp_result.ending_value))
    benchmark_final = Decimal(str(benchmark_result.ending_value))
    assumed_apr = Decimal(str(lp_result.fee_yield_pct)) / Decimal("100")
    days = Decimal(str((lp_result.end_timestamp - lp_result.start_timestamp).days))
    if days <= 0:
        return Decimal("0")
    lp_raw = lp_final / (Decimal("1") + (assumed_apr * days / Decimal("365.2425")))
    return (((benchmark_final / lp_raw) - Decimal("1")) * Decimal("365.2425") / days) * Decimal("100")


def format_break_even_summary(results):
    grouped = {}
    for result in results:
        key = (result.pair_name, result.start_timestamp.date().isoformat())
        grouped.setdefault(key, {})[result.strategy_name] = result

    lines = [
        "# Break-even APR Summary",
        "",
        "Break-even APR is the fixed LP fee APR needed for the LP to match each benchmark over the same historical window.",
        "",
        "Pair | Start | Vs Benchmark | Break-even APR %",
        "--- | --- | --- | ---:",
    ]
    for (pair_name, start), group in sorted(grouped.items()):
        lp_result = group.get(f"{pair_name}_lp_50_50")
        if lp_result is None:
            continue
        benchmarks = [
            group.get(f"{pair_name}_hold_50_50"),
            group.get(f"{pair_name}_hold_btc_usd"),
            group.get(f"{pair_name}_hold_eth_usd"),
            group.get(f"{pair_name}_hold_usdt_usd"),
        ]
        for benchmark in benchmarks:
            if benchmark is None:
                continue
            lines.append(
                f"{pair_name} | {start} | {benchmark.strategy_label} | {break_even_apr_pct(lp_result, benchmark):.2f}"
            )
    return "\n".join(lines) + "\n"


def save_results(output_root, results, manifest, run_id=None):
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = run_id or build_run_id()
    run_dir = output_root / run_id
    latest_dir = output_root / "latest"
    run_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    csv_path = run_dir / "lp_comparison_results.csv"
    md_path = run_dir / "lp_comparison_results.md"
    txt_path = run_dir / "lp_comparison_results.txt"
    manifest_path = run_dir / "manifest.json"
    break_even_path = run_dir / "break_even_summary.md"

    write_results_csv(csv_path, results)
    md_path.write_text(format_results_markdown(results))
    txt_path.write_text(format_results_table(results))
    write_manifest_json(manifest_path, manifest)
    break_even_path.write_text(format_break_even_summary(results))

    for source_path in [csv_path, md_path, txt_path, manifest_path, break_even_path]:
        shutil.copy2(source_path, latest_dir / source_path.name)

    return {
        "run_dir": run_dir,
        "latest_dir": latest_dir,
        "csv": csv_path,
        "markdown": md_path,
        "text": txt_path,
        "manifest": manifest_path,
        "break_even": break_even_path,
    }


def main():
    args = parse_args()
    since_dates = [parse_since(value) for value in (args.since or DEFAULT_SINCE_DATES)]
    pairs = args.pair or list(PAIR_CONFIGS.keys())
    pair_yields = {
        "wbtc-weth": args.wbtc_weth_yield_pct,
        "usdt-weth": args.usdt_weth_yield_pct,
    }
    results = run_lp_comparison_matrix(
        pairs=pairs,
        since_dates=since_dates,
        initial_value=args.initial_value,
        yield_mode=args.yield_mode,
        data_root=args.data_root,
        pair_yields=pair_yields,
    )
    manifest = build_manifest(args, since_dates, pairs)
    saved = save_results(args.output_dir, results, manifest)
    print(format_results_table(results))
    print(format_break_even_summary(results))
    print(f"Saved Manifest: {saved['manifest']}")


if __name__ == "__main__":
    main()
