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

from backtesting.multi_asset import MultiAssetSeries
from backtesting.portfolio_engine import PortfolioManagementBacktestEngine
from backtesting.portfolio_strategies import (
    BTCDefensiveETHAggressive,
    DrawdownTiltRebalance,
    NarrowCashBandRebalance,
    Static50_50Rebalance,
    Target50_50WithCashBand,
)
from backtesting.reporting import (
    format_results_markdown,
    format_results_table,
    group_results_by_keys,
    write_manifest_json,
    write_results_csv,
)
from backtesting.series import PriceSeries


UTC = timezone.utc
DEFAULT_DATA_ROOT = Path("data/market/coinbase")
DEFAULT_OUTPUT_DIR = Path("reports/portfolio_backtests")
DEFAULT_SINCE_DATES = ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"]
DEFAULT_INTERVAL_DAYS = [1, 2, 3, 5, 7]

LINE_WIDTH = 1400
LINE_HEIGHT = 800
LINE_PADDING = 90
PALETTE = {
    "static_50_50_rebalance": "#0f766e",
    "target_50_50_with_cash_band": "#dc2626",
    "narrow_cash_band_rebalance": "#2563eb",
    "drawdown_tilt_rebalance": "#7c3aed",
    "btc_defensive_eth_aggressive": "#b45309",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Compare BTC/ETH/DAI portfolio-management strategies.")
    parser.add_argument(
        "--since",
        action="append",
        help="Repeat to evaluate multiple start dates in YYYY-MM-DD.",
    )
    parser.add_argument(
        "--interval-days",
        action="append",
        type=int,
        help="Repeat to evaluate multiple rebalance cadences in days.",
    )
    parser.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--initial-btc", default="0.5")
    parser.add_argument("--initial-eth", default="5")
    parser.add_argument("--initial-dai", default="10000")
    parser.add_argument("--withdrawal-dai", default="0")
    parser.add_argument("--withdrawal-interval-days", type=int)
    return parser.parse_args()


def parse_since(value):
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def build_bundle(data_root):
    root = Path(data_root)
    return MultiAssetSeries(
        {
            "BTC-USD": PriceSeries.from_csv(root / "BTC-USD-1d.csv"),
            "ETH-USD": PriceSeries.from_csv(root / "ETH-USD-1d.csv"),
        }
    )


def build_portfolio_strategies():
    return [
        Static50_50Rebalance(),
        Target50_50WithCashBand(),
        NarrowCashBandRebalance(),
        DrawdownTiltRebalance(),
        BTCDefensiveETHAggressive(),
    ]


def run_portfolio_backtests(
    bundle,
    since_dates,
    interval_days_options,
    initial_btc,
    initial_eth,
    initial_dai,
    withdrawal_dai,
    withdrawal_interval_days,
):
    results = []
    for since in since_dates:
        for interval_days in interval_days_options:
            engine = PortfolioManagementBacktestEngine(
                interval_days=interval_days,
                withdrawal_amount_dai=withdrawal_dai,
                withdrawal_interval_days=withdrawal_interval_days,
            )
            for strategy in build_portfolio_strategies():
                results.append(
                    engine.run(
                        bundle,
                        strategy,
                        since,
                        initial_btc=initial_btc,
                        initial_eth=initial_eth,
                        initial_dai=initial_dai,
                    )
                )
    return results


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


def build_manifest(args, since_dates, interval_days_options):
    return {
        "generated_at_utc": datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "git_commit": get_git_commit(),
        "symbols": ["BTC-USD", "ETH-USD", "DAI"],
        "since_dates": [date.date().isoformat() for date in since_dates],
        "interval_days_options": list(interval_days_options),
        "initial_btc": str(args.initial_btc),
        "initial_eth": str(args.initial_eth),
        "initial_dai": str(args.initial_dai),
        "withdrawal_dai": str(args.withdrawal_dai),
        "withdrawal_interval_days": args.withdrawal_interval_days,
        "data_root": str(args.data_root),
        "data_files": {
            "BTC-USD": str(Path(args.data_root) / "BTC-USD-1d.csv"),
            "ETH-USD": str(Path(args.data_root) / "ETH-USD-1d.csv"),
        },
    }


def save_results(output_root, results, manifest, run_id=None):
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = run_id or build_run_id()
    run_dir = output_root / run_id
    latest_dir = output_root / "latest"
    run_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / "portfolio_strategy_results.csv"
    md_path = run_dir / "portfolio_strategy_results.md"
    txt_path = run_dir / "portfolio_strategy_results.txt"
    manifest_path = run_dir / "manifest.json"

    write_results_csv(csv_path, results)
    md_path.write_text(format_results_markdown(results))
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


def sanitize_filename(value):
    return value.replace(" ", "_").replace("/", "_")


def scale(value, min_value, max_value, out_min, out_max):
    if max_value == min_value:
        return (out_min + out_max) / 2
    ratio = (value - min_value) / (max_value - min_value)
    return out_min + (ratio * (out_max - out_min))


def render_equity_curve_svg(results, title, output_path):
    timestamps = sorted({point.timestamp for result in results for point in result.equity_curve})
    if not timestamps:
        raise ValueError("No equity curve points to plot")

    all_values = [float(point.portfolio_value) for result in results for point in result.equity_curve]
    min_y = min(all_values)
    max_y = max(all_values)
    min_x = 0
    max_x = max(len(result.equity_curve) for result in results) - 1

    plot_left = LINE_PADDING
    plot_right = LINE_WIDTH - LINE_PADDING
    plot_top = LINE_PADDING
    plot_bottom = LINE_HEIGHT - LINE_PADDING

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{LINE_WIDTH}" height="{LINE_HEIGHT}">',
        f'<rect width="{LINE_WIDTH}" height="{LINE_HEIGHT}" fill="#f8fafc"/>',
        f'<text x="{LINE_WIDTH / 2}" y="42" text-anchor="middle" font-family="monospace" font-size="24" fill="#0f172a">{title}</text>',
        f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" stroke="#334155" stroke-width="2"/>',
        f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" stroke="#334155" stroke-width="2"/>',
    ]

    for tick in range(6):
        x_index = min_x + ((max_x - min_x) * tick / 5 if max_x != min_x else 0)
        x_pos = scale(x_index, min_x, max_x, plot_left, plot_right)
        y_value = min_y + ((max_y - min_y) * tick / 5 if max_y != min_y else 0)
        y_pos = scale(y_value, min_y, max_y, plot_bottom, plot_top)
        elements.append(
            f'<line x1="{x_pos}" y1="{plot_bottom}" x2="{x_pos}" y2="{plot_top}" stroke="#cbd5e1" stroke-width="1"/>'
        )
        date_label = timestamps[int(round(x_index))].date().isoformat() if timestamps else ""
        elements.append(
            f'<text x="{x_pos}" y="{plot_bottom + 24}" text-anchor="middle" font-family="monospace" font-size="11" fill="#475569">{date_label}</text>'
        )
        elements.append(
            f'<line x1="{plot_left}" y1="{y_pos}" x2="{plot_right}" y2="{y_pos}" stroke="#cbd5e1" stroke-width="1"/>'
        )
        elements.append(
            f'<text x="{plot_left - 12}" y="{y_pos + 4}" text-anchor="end" font-family="monospace" font-size="12" fill="#475569">{y_value:.0f}</text>'
        )

    elements.append(
        f'<text x="{LINE_WIDTH / 2}" y="{LINE_HEIGHT - 18}" text-anchor="middle" font-family="monospace" font-size="16" fill="#0f172a">time</text>'
    )
    elements.append(
        f'<text x="24" y="{LINE_HEIGHT / 2}" transform="rotate(-90 24,{LINE_HEIGHT / 2})" text-anchor="middle" font-family="monospace" font-size="16" fill="#0f172a">portfolio_value_usd</text>'
    )

    legend_x = LINE_WIDTH - 430
    legend_y = 80
    for index, result in enumerate(results):
        y = legend_y + (index * 24)
        color = PALETTE.get(result.strategy_name, "#7c3aed")
        elements.append(f'<line x1="{legend_x}" y1="{y}" x2="{legend_x + 18}" y2="{y}" stroke="{color}" stroke-width="3"/>')
        elements.append(
            f'<text x="{legend_x + 28}" y="{y + 4}" font-family="monospace" font-size="12" fill="#0f172a">{result.strategy_name}</text>'
        )

    for result in results:
        color = PALETTE.get(result.strategy_name, "#7c3aed")
        points = []
        for index, point in enumerate(result.equity_curve):
            x = scale(index, min_x, max_x, plot_left, plot_right)
            y = scale(float(point.portfolio_value), min_y, max_y, plot_bottom, plot_top)
            points.append(f"{x},{y}")
        label = f"{result.strategy_name} | end={result.end_timestamp.date().isoformat()} | return={result.total_return_pct:.2f}%"
        elements.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2.5">'
            f"<title>{label}</title></polyline>"
        )

    elements.append("</svg>")
    output_path.write_text("\n".join(elements))


def write_equity_curve_plots(results, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped = group_results_by_keys(results, "start", "contribution_interval")
    written = []
    for (start, interval), scenario_results in sorted(grouped.items()):
        output_path = output_dir / f"portfolio_value_{sanitize_filename(start)}_{sanitize_filename(interval)}.svg"
        title = f"Portfolio Value Over Time | start={start} | interval={interval}"
        render_equity_curve_svg(scenario_results, title, output_path)
        written.append(output_path)
    return written


def copy_outputs_to_latest(paths, latest_dir):
    latest_dir = Path(latest_dir)
    latest_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        shutil.copy2(path, latest_dir / path.name)


def main():
    args = parse_args()
    since_dates = [parse_since(value) for value in (args.since or DEFAULT_SINCE_DATES)]
    interval_days_options = args.interval_days or DEFAULT_INTERVAL_DAYS
    bundle = build_bundle(args.data_root)
    results = run_portfolio_backtests(
        bundle=bundle,
        since_dates=since_dates,
        interval_days_options=interval_days_options,
        initial_btc=args.initial_btc,
        initial_eth=args.initial_eth,
        initial_dai=args.initial_dai,
        withdrawal_dai=args.withdrawal_dai,
        withdrawal_interval_days=args.withdrawal_interval_days,
    )
    manifest = build_manifest(args, since_dates, interval_days_options)
    saved_paths = save_results(args.output_dir, results, manifest)
    plot_paths = write_equity_curve_plots(results, saved_paths["run_dir"])
    copy_outputs_to_latest(plot_paths, saved_paths["latest_dir"])

    print(format_results_table(results))
    print()
    print(f"Run directory: {saved_paths['run_dir']}")
    print(f"Latest directory: {saved_paths['latest_dir']}")
    print(f"Saved CSV: {saved_paths['csv']}")
    print(f"Saved Markdown: {saved_paths['markdown']}")
    print(f"Saved Text: {saved_paths['text']}")
    print(f"Saved Manifest: {saved_paths['manifest']}")
    print(f"Saved equity curve plots: {len(plot_paths)}")


if __name__ == "__main__":
    main()
