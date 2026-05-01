#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


WIDTH = 1200
HEIGHT = 800
PADDING = 80
POINT_RADIUS = 5
PALETTE = {
    "BTC-USD": "#0f766e",
    "ETH-USD": "#2563eb",
    "BTC-USD+ETH-USD": "#b45309",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Plot scatter charts from backtest CSV results.")
    parser.add_argument("csv_path", help="Input results CSV")
    parser.add_argument(
        "--output-dir",
        help="Directory for SVG charts. Defaults to the CSV directory.",
    )
    return parser.parse_args()


def load_rows(csv_path):
    with open(csv_path, newline="") as handle:
        return list(csv.DictReader(handle))


def sanitize_label(row):
    return f"{row['symbol']} | {row['strategy_label']} | {row['start']}"


def scale(value, min_value, max_value, out_min, out_max):
    if max_value == min_value:
        return (out_min + out_max) / 2
    ratio = (value - min_value) / (max_value - min_value)
    return out_min + (ratio * (out_max - out_min))


def render_scatter_svg(rows, x_key, y_key, title, output_path):
    x_values = [float(row[x_key]) for row in rows]
    y_values = [float(row[y_key]) for row in rows]
    min_x, max_x = min(x_values), max(x_values)
    min_y, max_y = min(y_values), max(y_values)

    plot_left = PADDING
    plot_right = WIDTH - PADDING
    plot_top = PADDING
    plot_bottom = HEIGHT - PADDING

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#f8fafc"/>',
        f'<text x="{WIDTH / 2}" y="40" text-anchor="middle" font-family="monospace" font-size="24" fill="#0f172a">{title}</text>',
        f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" stroke="#334155" stroke-width="2"/>',
        f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" stroke="#334155" stroke-width="2"/>',
    ]

    for tick in range(6):
        x_value = min_x + ((max_x - min_x) * tick / 5 if max_x != min_x else 0)
        x_pos = scale(x_value, min_x, max_x, plot_left, plot_right)
        y_value = min_y + ((max_y - min_y) * tick / 5 if max_y != min_y else 0)
        y_pos = scale(y_value, min_y, max_y, plot_bottom, plot_top)
        elements.append(
            f'<line x1="{x_pos}" y1="{plot_bottom}" x2="{x_pos}" y2="{plot_top}" stroke="#cbd5e1" stroke-width="1"/>'
        )
        elements.append(
            f'<text x="{x_pos}" y="{plot_bottom + 24}" text-anchor="middle" font-family="monospace" font-size="12" fill="#475569">{x_value:.2f}</text>'
        )
        elements.append(
            f'<line x1="{plot_left}" y1="{y_pos}" x2="{plot_right}" y2="{y_pos}" stroke="#cbd5e1" stroke-width="1"/>'
        )
        elements.append(
            f'<text x="{plot_left - 12}" y="{y_pos + 4}" text-anchor="end" font-family="monospace" font-size="12" fill="#475569">{y_value:.2f}</text>'
        )

    elements.append(
        f'<text x="{WIDTH / 2}" y="{HEIGHT - 18}" text-anchor="middle" font-family="monospace" font-size="16" fill="#0f172a">{x_key}</text>'
    )
    elements.append(
        f'<text x="24" y="{HEIGHT / 2}" transform="rotate(-90 24,{HEIGHT / 2})" text-anchor="middle" font-family="monospace" font-size="16" fill="#0f172a">{y_key}</text>'
    )

    legend_x = WIDTH - 260
    legend_y = 70
    legend_items = list(PALETTE.items())
    for index, (symbol, color) in enumerate(legend_items):
        y = legend_y + (index * 24)
        elements.append(f'<circle cx="{legend_x}" cy="{y}" r="6" fill="{color}"/>')
        elements.append(
            f'<text x="{legend_x + 14}" y="{y + 4}" font-family="monospace" font-size="12" fill="#0f172a">{symbol}</text>'
        )

    for row in rows:
        x = scale(float(row[x_key]), min_x, max_x, plot_left, plot_right)
        y = scale(float(row[y_key]), min_y, max_y, plot_bottom, plot_top)
        color = PALETTE.get(row["symbol"], "#7c3aed")
        label = sanitize_label(row)
        elements.append(
            f'<circle cx="{x}" cy="{y}" r="{POINT_RADIUS}" fill="{color}">'
            f'<title>{label}</title></circle>'
        )

    elements.append("</svg>")
    output_path.write_text("\n".join(elements))


def plot_all(csv_path, output_dir):
    rows = load_rows(csv_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    render_scatter_svg(
        rows,
        "max_drawdown_pct",
        "return_pct",
        "Return vs Max Drawdown",
        output_dir / "return_vs_drawdown.svg",
    )
    render_scatter_svg(
        rows,
        "deployment_pct",
        "return_pct",
        "Return vs Deployment",
        output_dir / "return_vs_deployment.svg",
    )


def main():
    args = parse_args()
    csv_path = Path(args.csv_path)
    output_dir = Path(args.output_dir) if args.output_dir else csv_path.parent
    plot_all(csv_path, output_dir)


if __name__ == "__main__":
    main()
