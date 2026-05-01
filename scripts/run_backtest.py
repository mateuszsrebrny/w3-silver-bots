#!/usr/bin/env python3

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtesting.engine import BacktestEngine
from backtesting.multi_asset import MultiAssetSeries
from backtesting.reporting import (
    format_results_table,
    write_manifest_json,
    write_results_csv,
    write_results_markdown,
)
from backtesting.rotation_engine import RotationBacktestEngine
from backtesting.rotation_strategies import (
    BTCOnlyWeekly,
    BTCCoreETHOverlay,
    BuyBTCBelowMAOtherwiseETH,
    BuyETHBelowMAOtherwiseBTC,
    BuyFurtherBelowMAWeekly,
    BuyStrongerReturnWeekly,
    BuyWeakerReturnWeekly,
    ETHOnlyWeekly,
    EqualSplitWeekly,
    RiskOnETHRiskOffBTC,
)
from backtesting.series import PriceSeries
from backtesting.strategies import (
    WeeklyDipDCA,
    WeeklyDrawdownScaledDCA,
    WeeklyFixedDCA,
    WeeklyMAScaledDCA,
    WeeklyMATrendDCA,
)


UTC = timezone.utc
DEFAULT_DATA_ROOT = Path("data/market/coinbase")
DEFAULT_OUTPUT_DIR = Path("reports/backtests")
DEFAULT_SYMBOLS = ["BTC-USD", "ETH-USD"]
DEFAULT_SINCE_DATES = ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"]
DEFAULT_MA_WINDOWS = [20, 50, 100, 200]
DEFAULT_DUAL_RETURN_WINDOWS = [28, 84]
DEFAULT_INTERVAL_DAYS = [1, 2, 3, 5]


def parse_args():
    parser = argparse.ArgumentParser(description="Compare Sunday DCA backtest strategies.")
    parser.add_argument(
        "--symbol",
        action="append",
        choices=["BTC-USD", "ETH-USD"],
        help="Repeat to evaluate multiple symbols.",
    )
    parser.add_argument(
        "--since",
        action="append",
        help="Repeat to evaluate multiple start dates in YYYY-MM-DD.",
    )
    parser.add_argument("--weekly-amount", default="100")
    parser.add_argument(
        "--ma-window",
        action="append",
        type=int,
        help="Repeat to evaluate multiple moving-average windows.",
    )
    parser.add_argument(
        "--interval-days",
        action="append",
        type=int,
        help="Repeat to evaluate multiple contribution cadences in days.",
    )
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--strategy-set",
        default="all",
        choices=["single", "dual", "all"],
    )
    return parser.parse_args()


def build_series(symbol, data_root):
    path = Path(data_root) / f"{symbol}-1d.csv"
    return PriceSeries.from_csv(path)


def build_strategies(weekly_amount, ma_window):
    return [
        WeeklyFixedDCA(weekly_amount),
        WeeklyMATrendDCA(weekly_amount, window_days=ma_window),
        WeeklyDipDCA(weekly_amount, window_days=ma_window),
        WeeklyMAScaledDCA(weekly_amount, window_days=ma_window),
    ]


def build_ma_independent_strategies(weekly_amount):
    return [
        WeeklyDrawdownScaledDCA(weekly_amount),
    ]


def build_dual_asset_strategies(return_windows):
    strategies = [
        BTCOnlyWeekly(),
        ETHOnlyWeekly(),
        EqualSplitWeekly(),
        RiskOnETHRiskOffBTC(window_days=50),
        BuyFurtherBelowMAWeekly(window_days=50),
        BuyETHBelowMAOtherwiseBTC(window_days=50),
        BuyBTCBelowMAOtherwiseETH(window_days=50),
        BTCCoreETHOverlay(ma_window_days=50, return_window_days=84, eth_weight="0.30"),
    ]
    for window_days in return_windows:
        strategies.append(BuyStrongerReturnWeekly(window_days))
        strategies.append(BuyWeakerReturnWeekly(window_days))
    return strategies


def parse_since(value):
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def run_backtests(symbol, since, weekly_amount, ma_window, interval_days, data_root):
    series = build_series(symbol, data_root)
    engine = BacktestEngine(weekly_amount, interval_days=interval_days)
    results = [
        engine.run(series, strategy, since)
        for strategy in build_strategies(weekly_amount, ma_window)
    ]
    return results


def run_dual_asset_backtests(symbols, since, weekly_amount, interval_days, return_windows, data_root):
    series_by_symbol = {
        symbol: build_series(symbol, data_root)
        for symbol in symbols
    }
    bundle = MultiAssetSeries(series_by_symbol)
    engine = RotationBacktestEngine(weekly_amount, interval_days=interval_days)
    return [
        engine.run(bundle, strategy, since)
        for strategy in build_dual_asset_strategies(return_windows)
    ]


def run_experiment_matrix(symbols, since_dates, weekly_amount, ma_windows, interval_days_options, data_root):
    all_results = []
    for symbol in symbols:
        for since in since_dates:
            for interval_days in interval_days_options:
                fixed_results = run_backtests(
                    symbol=symbol,
                    since=since,
                    weekly_amount=weekly_amount,
                    ma_window=ma_windows[0],
                    interval_days=interval_days,
                    data_root=data_root,
                )
                all_results.append(fixed_results[0])

                for ma_window in ma_windows:
                    ma_results = run_backtests(
                        symbol=symbol,
                        since=since,
                        weekly_amount=weekly_amount,
                        ma_window=ma_window,
                        interval_days=interval_days,
                        data_root=data_root,
                    )
                    all_results.extend(ma_results[1:])

                series = build_series(symbol, data_root)
                engine = BacktestEngine(weekly_amount, interval_days=interval_days)
                all_results.extend(
                    engine.run(series, strategy, since)
                    for strategy in build_ma_independent_strategies(weekly_amount)
                )
    return all_results


def run_dual_experiment_matrix(symbols, since_dates, weekly_amount, interval_days_options, return_windows, data_root):
    all_results = []
    for since in since_dates:
        for interval_days in interval_days_options:
            all_results.extend(
                run_dual_asset_backtests(
                    symbols=symbols,
                    since=since,
                    weekly_amount=weekly_amount,
                    interval_days=interval_days,
                    return_windows=return_windows,
                    data_root=data_root,
                )
            )
    return all_results


def get_git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        return None


def build_run_id(now=None):
    now = now or datetime.now(tz=UTC)
    return now.strftime("%Y%m%d-%H%M%S")


def save_results(output_root, results, manifest, run_id=None):
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = run_id or build_run_id()
    run_dir = output_root / run_id
    latest_dir = output_root / "latest"
    run_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / "dca_strategy_results.csv"
    md_path = run_dir / "dca_strategy_results.md"
    txt_path = run_dir / "dca_strategy_results.txt"
    manifest_path = run_dir / "manifest.json"

    write_results_csv(csv_path, results)
    write_results_markdown(md_path, results)
    txt_path.write_text(format_results_table(results))
    write_manifest_json(manifest_path, manifest)

    for source_path in [csv_path, md_path, txt_path, manifest_path]:
        shutil.copy2(source_path, latest_dir / source_path.name)

    return {
        "run_dir": run_dir,
        "latest_dir": latest_dir,
        "csv": csv_path,
        "markdown": md_path,
        "text": txt_path,
        "manifest": manifest_path,
    }


def build_manifest(
    strategy_set,
    symbols,
    since_dates,
    weekly_amount,
    ma_windows,
    interval_days_options,
    dual_return_windows,
    data_root,
):
    return {
        "generated_at_utc": datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "git_commit": get_git_commit(),
        "strategy_set": strategy_set,
        "symbols": list(symbols),
        "since_dates": [date.date().isoformat() for date in since_dates],
        "weekly_amount_usd": str(weekly_amount),
        "single_asset_ma_windows": list(ma_windows),
        "interval_days_options": list(interval_days_options),
        "dual_asset_return_windows": list(dual_return_windows),
        "data_root": str(data_root),
        "data_files": {
            symbol: str(Path(data_root) / f"{symbol}-1d.csv")
            for symbol in symbols
        },
    }


def main():
    args = parse_args()
    symbols = args.symbol or DEFAULT_SYMBOLS
    since_dates = [parse_since(value) for value in (args.since or DEFAULT_SINCE_DATES)]
    ma_windows = args.ma_window or DEFAULT_MA_WINDOWS
    interval_days_options = args.interval_days or DEFAULT_INTERVAL_DAYS
    results = []
    if args.strategy_set in ["single", "all"]:
        results.extend(
            run_experiment_matrix(
                symbols=symbols,
                since_dates=since_dates,
                weekly_amount=args.weekly_amount,
                ma_windows=ma_windows,
                interval_days_options=interval_days_options,
                data_root=args.data_root,
            )
        )
    if args.strategy_set in ["dual", "all"]:
        results.extend(
            run_dual_experiment_matrix(
                symbols=DEFAULT_SYMBOLS,
                since_dates=since_dates,
                weekly_amount=args.weekly_amount,
                interval_days_options=interval_days_options,
                return_windows=DEFAULT_DUAL_RETURN_WINDOWS,
                data_root=args.data_root,
            )
        )

    manifest = build_manifest(
        strategy_set=args.strategy_set,
        symbols=symbols if args.strategy_set != "dual" else DEFAULT_SYMBOLS,
        since_dates=since_dates,
        weekly_amount=args.weekly_amount,
        ma_windows=ma_windows,
        interval_days_options=interval_days_options,
        dual_return_windows=DEFAULT_DUAL_RETURN_WINDOWS,
        data_root=args.data_root,
    )
    saved_paths = save_results(args.output_dir, results, manifest)
    print(format_results_table(results))
    print()
    print(f"Run directory: {saved_paths['run_dir']}")
    print(f"Latest directory: {saved_paths['latest_dir']}")
    print(f"Saved CSV: {saved_paths['csv']}")
    print(f"Saved Markdown: {saved_paths['markdown']}")
    print(f"Saved Text: {saved_paths['text']}")
    print(f"Saved Manifest: {saved_paths['manifest']}")


if __name__ == "__main__":
    main()
