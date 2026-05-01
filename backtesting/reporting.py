import csv
import json
from decimal import Decimal, ROUND_HALF_UP


def quantize_money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def result_to_row(result):
    return {
        "strategy": result.strategy_name,
        "strategy_label": result.strategy_label,
        "symbol": result.symbol,
        "contribution_interval": result.contribution_interval,
        "start": result.start_timestamp.date().isoformat(),
        "end": result.end_timestamp.date().isoformat(),
        "contributed_usd": str(quantize_money(result.total_contributed)),
        "invested_usd": str(quantize_money(result.total_invested)),
        "ending_cash_usd": str(quantize_money(result.ending_cash)),
        "ending_value_usd": str(quantize_money(result.ending_value)),
        "return_pct": str(quantize_money(result.total_return_pct)),
        "deployment_pct": str(quantize_money(result.deployment_rate_pct)),
        "max_drawdown_pct": str(quantize_money(result.max_drawdown_pct)),
        "trade_count": str(result.trade_count),
    }


def format_results_table(results):
    rows = [result_to_row(result) for result in results]
    headers = [
        "strategy",
        "strategy_label",
        "symbol",
        "contribution_interval",
        "start",
        "end",
        "contributed_usd",
        "invested_usd",
        "ending_cash_usd",
        "ending_value_usd",
        "return_pct",
        "deployment_pct",
        "max_drawdown_pct",
        "trade_count",
    ]

    widths = {
        header: max(len(header), *(len(row[header]) for row in rows))
        for header in headers
    }

    lines = [
        " ".join(header.ljust(widths[header]) for header in headers),
        " ".join("-" * widths[header] for header in headers),
    ]
    for row in rows:
        lines.append(" ".join(row[header].ljust(widths[header]) for header in headers))
    return "\n".join(lines)


def write_results_csv(path, results):
    rows = [result_to_row(result) for result in results]
    if not rows:
        raise ValueError("No results to write")

    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def format_results_markdown(results):
    rows = [result_to_row(result) for result in results]
    headers = list(rows[0].keys())
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines = [
        "| " + " | ".join(row[header] for header in headers) + " |"
        for row in rows
    ]
    return "\n".join([header_line, separator_line, *body_lines])


def write_results_markdown(path, results):
    with open(path, "w") as handle:
        handle.write(format_results_markdown(results))


def write_manifest_json(path, manifest):
    with open(path, "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
