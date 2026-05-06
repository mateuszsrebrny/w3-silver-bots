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
WEEKLY_INTERVAL = "7d"
TOP_STRATEGY_LIMIT = 3

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
ASSET_COLORS = {
    "DAI": "#facc15",
    "ETH-USD": "#2563eb",
    "BTC-USD": "#f97316",
}
ACTION_COLORS = {
    "hold": "#94a3b8",
    "buy_btc": "#ea580c",
    "buy_eth": "#2563eb",
    "buy_btc+buy_eth": "#16a34a",
    "sell_btc": "#dc2626",
    "sell_eth": "#7c3aed",
    "sell_btc+sell_eth": "#0f172a",
    "buy_btc+sell_eth": "#0891b2",
    "sell_btc+buy_eth": "#c026d3",
}
TRADE_PANEL_COLORS = {
    "BTC-USD": {
        "buy": "#ea580c",
        "sell": "#dc2626",
    },
    "ETH-USD": {
        "buy": "#2563eb",
        "sell": "#7c3aed",
    },
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


def _monthly_tick_indices(allocation_curve):
    ticks = []
    seen = set()
    for index, point in enumerate(allocation_curve):
        key = (point.timestamp.year, point.timestamp.month)
        if key in seen:
            continue
        seen.add(key)
        ticks.append((index, point.timestamp.strftime("%Y-%m")))
    return ticks


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


def _weekly_results(results):
    return [result for result in results if result.contribution_interval == WEEKLY_INTERVAL]


def _mean(values):
    return sum(values) / len(values) if values else 0


def rank_top_weekly_strategies(results, limit=TOP_STRATEGY_LIMIT):
    weekly_results = _weekly_results(results)
    strategy_rows = {}
    for result in weekly_results:
        strategy_rows.setdefault(result.strategy_name, []).append(result)

    ranking = []
    for strategy_name, strategy_results in strategy_rows.items():
        returns = [float(result.total_return_pct) for result in strategy_results]
        ranking.append(
            {
                "strategy_name": strategy_name,
                "results": strategy_results,
                "mean_return_pct": _mean(returns),
                "min_return_pct": min(returns),
                "max_return_pct": max(returns),
            }
        )

    ranking.sort(key=lambda row: row["mean_return_pct"], reverse=True)
    return ranking[:limit]


def format_top_weekly_strategy_summary(results, limit=TOP_STRATEGY_LIMIT):
    ranking = rank_top_weekly_strategies(results, limit=limit)
    if not ranking:
        return "No weekly portfolio results available."

    lines = [
        "# Top Weekly Portfolio Strategies",
        "",
        "Rank | Strategy | Mean Return % | Min Return % | Max Return %",
        "--- | --- | ---: | ---: | ---:",
    ]
    for index, row in enumerate(ranking, start=1):
        lines.append(
            f"{index} | {row['strategy_name']} | "
            f"{row['mean_return_pct']:.2f} | {row['min_return_pct']:.2f} | {row['max_return_pct']:.2f}"
        )

    lines.extend(["", "## Weekly Returns By Start Date", ""])
    for row in ranking:
        lines.append(f"### {row['strategy_name']}")
        lines.append("")
        lines.append("Start | Return % | Max Drawdown % | Ending Value USD | Trades")
        lines.append("--- | ---: | ---: | ---: | ---:")
        for result in sorted(row["results"], key=lambda item: item.start_timestamp):
            lines.append(
                f"{result.start_timestamp.date().isoformat()} | "
                f"{float(result.total_return_pct):.2f} | "
                f"{float(result.max_drawdown_pct):.2f} | "
                f"{float(result.ending_value):.2f} | "
                f"{result.trade_count}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_top_weekly_strategy_summary(results, output_path, limit=TOP_STRATEGY_LIMIT):
    output_path = Path(output_path)
    output_path.write_text(format_top_weekly_strategy_summary(results, limit=limit))
    return output_path


def _render_stacked_band(allocation_curve, key, lower_values, upper_values, min_y, max_y, plot_left, plot_right, plot_top, plot_bottom):
    top_points = []
    bottom_points = []
    max_x = max(len(allocation_curve) - 1, 1)

    for index, point in enumerate(allocation_curve):
        x = scale(index, 0, max_x, plot_left, plot_right)
        top_y = scale(upper_values[index], min_y, max_y, plot_bottom, plot_top)
        bottom_y = scale(lower_values[index], min_y, max_y, plot_bottom, plot_top)
        top_points.append(f"{x},{top_y}")
        bottom_points.append(f"{x},{bottom_y}")

    color = ASSET_COLORS[key]
    polygon = " ".join(top_points + list(reversed(bottom_points)))
    return f'<polygon points="{polygon}" fill="{color}" fill-opacity="0.70" stroke="{color}" stroke-width="1.2"/>'


def _build_trade_notional_series(result, symbol):
    by_timestamp = {}
    for trade in result.trades:
        if trade.symbol != symbol:
            continue
        signed = trade.notional_usd if trade.side == "buy" else -trade.notional_usd
        by_timestamp[trade.timestamp] = by_timestamp.get(trade.timestamp, 0) + float(signed)
    return [by_timestamp.get(point.timestamp, 0.0) for point in result.allocation_curve]


def _render_trade_notional_panel(elements, allocation_curve, series, symbol, plot_left, plot_right, plot_top, plot_bottom):
    max_x = max(len(allocation_curve) - 1, 1)
    abs_max = max([abs(value) for value in series] + [1.0])
    zero_y = scale(0.0, -abs_max, abs_max, plot_bottom, plot_top)
    asset_label = symbol.replace("-USD", "")

    elements.append(f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" stroke="#334155" stroke-width="2"/>')
    elements.append(f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" stroke="#334155" stroke-width="2"/>')
    elements.append(f'<line x1="{plot_left}" y1="{zero_y}" x2="{plot_right}" y2="{zero_y}" stroke="#64748b" stroke-width="1.5" stroke-dasharray="6 4"/>')

    for tick in range(3):
        y_value = -abs_max + ((2 * abs_max) * tick / 2)
        y_pos = scale(y_value, -abs_max, abs_max, plot_bottom, plot_top)
        elements.append(f'<line x1="{plot_left}" y1="{y_pos}" x2="{plot_right}" y2="{y_pos}" stroke="#e2e8f0" stroke-width="1"/>')
        elements.append(
            f'<text x="{plot_left - 12}" y="{y_pos + 4}" text-anchor="end" font-family="monospace" font-size="11" fill="#475569">{y_value:.0f}</text>'
        )

    bar_width = max(4, ((plot_right - plot_left) / max(len(allocation_curve), 2)) * 0.55)
    for index, value in enumerate(series):
        x = scale(index, 0, max_x, plot_left, plot_right)
        y_value = scale(value, -abs_max, abs_max, plot_bottom, plot_top)
        top_y = min(y_value, zero_y)
        height = max(abs(zero_y - y_value), 1.5)
        side = "buy" if value >= 0 else "sell"
        color = TRADE_PANEL_COLORS[symbol][side]
        point = allocation_curve[index]
        elements.append(
            f'<rect x="{x - (bar_width / 2)}" y="{top_y}" width="{bar_width}" height="{height}" fill="{color}" opacity="0.85">'
            f"<title>{point.timestamp.date().isoformat()} | {asset_label} {side} {abs(value):.2f} usd | reason={point.decision_reason}</title>"
            f"</rect>"
        )

    elements.append(
        f'<text x="24" y="{(plot_top + plot_bottom) / 2}" transform="rotate(-90 24,{(plot_top + plot_bottom) / 2})" text-anchor="middle" font-family="monospace" font-size="14" fill="#0f172a">{asset_label} weekly trade usd</text>'
    )


def render_weekly_allocation_action_svg(result, output_path):
    allocation_curve = result.allocation_curve
    if not allocation_curve:
        raise ValueError("No allocation curve points to plot")

    plot_left = LINE_PADDING
    plot_right = LINE_WIDTH - LINE_PADDING
    plot_top = LINE_PADDING
    plot_bottom = 420
    btc_top = 480
    btc_bottom = 605
    eth_top = 645
    eth_bottom = 770

    totals = [float(point.total_value) for point in allocation_curve]
    max_total = max(totals)
    max_x = max(len(allocation_curve) - 1, 1)
    month_ticks = _monthly_tick_indices(allocation_curve)

    dai_values = [float(point.dai_value) for point in allocation_curve]
    eth_values = [float(point.eth_value) for point in allocation_curve]
    btc_values = [float(point.btc_value) for point in allocation_curve]
    dai_upper = dai_values
    eth_upper = [dai_values[index] + eth_values[index] for index in range(len(allocation_curve))]
    btc_upper = [eth_upper[index] + btc_values[index] for index in range(len(allocation_curve))]

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{LINE_WIDTH}" height="{LINE_HEIGHT}">',
        f'<rect width="{LINE_WIDTH}" height="{LINE_HEIGHT}" fill="#f8fafc"/>',
        f'<text x="{LINE_WIDTH / 2}" y="42" text-anchor="middle" font-family="monospace" font-size="24" fill="#0f172a">'
        f'{result.strategy_name} | weekly | start={result.start_timestamp.date().isoformat()} | return={float(result.total_return_pct):.2f}%</text>',
        f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" stroke="#334155" stroke-width="2"/>',
        f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" stroke="#334155" stroke-width="2"/>',
    ]

    for index_value, month_label in month_ticks:
        x_pos = scale(index_value, 0, max_x, plot_left, plot_right)
        elements.append(f'<line x1="{x_pos}" y1="{plot_bottom}" x2="{x_pos}" y2="{plot_top}" stroke="#94a3b8" stroke-width="1.2"/>')
        elements.append(f'<line x1="{x_pos}" y1="{btc_bottom}" x2="{x_pos}" y2="{btc_top}" stroke="#94a3b8" stroke-width="1.2"/>')
        elements.append(f'<line x1="{x_pos}" y1="{eth_bottom}" x2="{x_pos}" y2="{eth_top}" stroke="#94a3b8" stroke-width="1.2"/>')
        elements.append(
            f'<text x="{x_pos}" y="{eth_bottom + 18}" text-anchor="middle" font-family="monospace" font-size="11" fill="#334155">{month_label}</text>'
        )

    for tick in range(6):
        total_value = max_total * tick / 5 if max_total else 0
        y_pos = scale(total_value, 0, max_total, plot_bottom, plot_top) if max_total else (plot_top + plot_bottom) / 2
        elements.append(f'<line x1="{plot_left}" y1="{y_pos}" x2="{plot_right}" y2="{y_pos}" stroke="#cbd5e1" stroke-width="1"/>')
        elements.append(
            f'<text x="{plot_left - 12}" y="{y_pos + 4}" text-anchor="end" font-family="monospace" font-size="12" fill="#475569">{total_value:.0f}</text>'
        )

    elements.append(_render_stacked_band(allocation_curve, "DAI", [0.0] * len(allocation_curve), dai_upper, 0, max_total, plot_left, plot_right, plot_top, plot_bottom))
    elements.append(_render_stacked_band(allocation_curve, "ETH-USD", dai_upper, eth_upper, 0, max_total, plot_left, plot_right, plot_top, plot_bottom))
    elements.append(_render_stacked_band(allocation_curve, "BTC-USD", eth_upper, btc_upper, 0, max_total, plot_left, plot_right, plot_top, plot_bottom))

    legend_x = LINE_WIDTH - 300
    legend_y = 86
    for index, asset in enumerate(["BTC-USD", "ETH-USD", "DAI"]):
        y = legend_y + (index * 22)
        color = ASSET_COLORS[asset]
        label = asset.replace("-USD", "")
        elements.append(f'<rect x="{legend_x}" y="{y - 10}" width="16" height="12" fill="{color}" fill-opacity="0.70" stroke="{color}"/>')
        elements.append(f'<text x="{legend_x + 24}" y="{y}" font-family="monospace" font-size="12" fill="#0f172a">{label}</text>')

    elements.append(
        f'<text x="{LINE_WIDTH / 2}" y="{LINE_HEIGHT - 18}" text-anchor="middle" font-family="monospace" font-size="16" fill="#0f172a">time</text>'
    )
    elements.append(
        f'<text x="24" y="{(plot_top + plot_bottom) / 2}" transform="rotate(-90 24,{(plot_top + plot_bottom) / 2})" text-anchor="middle" font-family="monospace" font-size="16" fill="#0f172a">asset value split (usd)</text>'
    )

    btc_series = _build_trade_notional_series(result, "BTC-USD")
    eth_series = _build_trade_notional_series(result, "ETH-USD")
    _render_trade_notional_panel(elements, allocation_curve, btc_series, "BTC-USD", plot_left, plot_right, btc_top, btc_bottom)
    _render_trade_notional_panel(elements, allocation_curve, eth_series, "ETH-USD", plot_left, plot_right, eth_top, eth_bottom)

    legend_action_x = LINE_WIDTH - 360
    legend_action_y = btc_top + 8
    legend_entries = [
        ("BTC buy", TRADE_PANEL_COLORS["BTC-USD"]["buy"]),
        ("BTC sell", TRADE_PANEL_COLORS["BTC-USD"]["sell"]),
        ("ETH buy", TRADE_PANEL_COLORS["ETH-USD"]["buy"]),
        ("ETH sell", TRADE_PANEL_COLORS["ETH-USD"]["sell"]),
    ]
    for index, (label, color) in enumerate(legend_entries):
        x = legend_action_x + (index % 2) * 150
        y = legend_action_y + (index // 2) * 20
        elements.append(f'<rect x="{x}" y="{y - 10}" width="14" height="10" fill="{color}" opacity="0.85"/>')
        elements.append(f'<text x="{x + 22}" y="{y}" font-family="monospace" font-size="11" fill="#0f172a">{label}</text>')

    elements.append("</svg>")
    output_path.write_text("\n".join(elements))


def write_top_weekly_strategy_plots(results, output_dir, limit=TOP_STRATEGY_LIMIT):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ranking = rank_top_weekly_strategies(results, limit=limit)
    if not ranking:
        return []

    keep_names = {row["strategy_name"] for row in ranking}
    written = []
    for result in sorted(_weekly_results(results), key=lambda item: (item.strategy_name, item.start_timestamp)):
        if result.strategy_name not in keep_names:
            continue
        output_path = output_dir / (
            f"weekly_strategy_{sanitize_filename(result.strategy_name)}_"
            f"{result.start_timestamp.date().isoformat()}.svg"
        )
        render_weekly_allocation_action_svg(result, output_path)
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
    run_dir = Path(saved_paths["run_dir"])
    latest_dir = Path(saved_paths["latest_dir"])
    plot_paths = write_equity_curve_plots(results, run_dir)
    weekly_plot_paths = write_top_weekly_strategy_plots(results, run_dir)
    weekly_summary_path = write_top_weekly_strategy_summary(results, run_dir / "weekly_top3_summary.md")
    copy_outputs_to_latest(plot_paths, latest_dir)
    copy_outputs_to_latest(weekly_plot_paths + [weekly_summary_path], latest_dir)

    print(format_results_table(results))
    print()
    print(format_top_weekly_strategy_summary(results))
    print()
    print(f"Run directory: {saved_paths['run_dir']}")
    print(f"Latest directory: {saved_paths['latest_dir']}")
    print(f"Saved CSV: {saved_paths['csv']}")
    print(f"Saved Markdown: {saved_paths['markdown']}")
    print(f"Saved Text: {saved_paths['text']}")
    print(f"Saved Manifest: {saved_paths['manifest']}")
    print(f"Saved equity curve plots: {len(plot_paths)}")
    print(f"Saved weekly top strategy plots: {len(weekly_plot_paths)}")
    print(f"Saved weekly top strategy summary: {weekly_summary_path}")


if __name__ == "__main__":
    main()
