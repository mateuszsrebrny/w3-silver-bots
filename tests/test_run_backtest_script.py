from datetime import datetime, timezone
from pathlib import Path
import json
import sys

from scripts import run_backtest


UTC = timezone.utc


def test_parse_since_returns_utc_datetime():
    assert run_backtest.parse_since("2020-01-01") == datetime(2020, 1, 1, tzinfo=UTC)


def test_main_passes_arguments_to_runner(monkeypatch, capsys):
    captured = {}

    def fake_run_experiment_matrix(symbols, since_dates, weekly_amount, ma_windows, interval_days_options, data_root):
        captured["symbols"] = symbols
        captured["since_dates"] = since_dates
        captured["weekly_amount"] = weekly_amount
        captured["ma_windows"] = ma_windows
        captured["interval_days_options"] = interval_days_options
        captured["data_root"] = data_root
        return ["fake-results"]

    def fake_run_dual_experiment_matrix(symbols, since_dates, weekly_amount, interval_days_options, return_windows, data_root):
        captured["dual_symbols"] = symbols
        captured["dual_since_dates"] = since_dates
        captured["dual_weekly_amount"] = weekly_amount
        captured["dual_interval_days_options"] = interval_days_options
        captured["dual_return_windows"] = return_windows
        captured["dual_data_root"] = data_root
        return ["fake-dual-results"]

    monkeypatch.setattr(run_backtest, "run_experiment_matrix", fake_run_experiment_matrix)
    monkeypatch.setattr(run_backtest, "run_dual_experiment_matrix", fake_run_dual_experiment_matrix)
    monkeypatch.setattr(
        run_backtest,
        "save_results",
        lambda output_dir, results, manifest: {
            "run_dir": f"{output_dir}/run",
            "latest_dir": f"{output_dir}/latest",
            "csv": f"{output_dir}/results.csv",
            "markdown": f"{output_dir}/results.md",
            "text": f"{output_dir}/results.txt",
            "manifest": f"{output_dir}/manifest.json",
        },
    )
    monkeypatch.setattr(run_backtest, "format_results_table", lambda results: f"table={results}")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_backtest.py",
            "--symbol",
            "ETH-USD",
            "--symbol",
            "BTC-USD",
            "--since",
            "2021-01-01",
            "--since",
            "2022-01-01",
            "--weekly-amount",
            "150",
            "--ma-window",
            "30",
            "--ma-window",
            "60",
            "--interval-days",
            "1",
            "--interval-days",
            "5",
            "--data-root",
            "custom-data",
            "--output-dir",
            "custom-reports",
            "--strategy-set",
            "all",
        ],
    )

    run_backtest.main()

    assert captured == {
        "symbols": ["ETH-USD", "BTC-USD"],
        "since_dates": [
            datetime(2021, 1, 1, tzinfo=UTC),
            datetime(2022, 1, 1, tzinfo=UTC),
        ],
        "weekly_amount": "150",
        "ma_windows": [30, 60],
        "interval_days_options": [1, 5],
        "data_root": "custom-data",
        "dual_symbols": ["BTC-USD", "ETH-USD"],
        "dual_since_dates": [
            datetime(2021, 1, 1, tzinfo=UTC),
            datetime(2022, 1, 1, tzinfo=UTC),
        ],
        "dual_weekly_amount": "150",
        "dual_interval_days_options": [1, 5],
        "dual_return_windows": [28, 84],
        "dual_data_root": "custom-data",
    }
    output = capsys.readouterr().out
    assert "table=['fake-results', 'fake-dual-results']" in output
    assert "Saved Manifest: custom-reports/manifest.json" in output


def test_run_experiment_matrix_runs_fixed_once_per_symbol_since(monkeypatch):
    calls = []

    def fake_run_backtests(symbol, since, weekly_amount, ma_window, interval_days, data_root):
        calls.append((symbol, since, weekly_amount, ma_window, interval_days, data_root))
        return [f"fixed-{symbol}-{since.date()}-{interval_days}", f"trend-{ma_window}-{interval_days}", f"dip-{ma_window}-{interval_days}"]

    monkeypatch.setattr(run_backtest, "run_backtests", fake_run_backtests)
    monkeypatch.setattr(run_backtest, "build_series", lambda symbol, data_root: "series")

    class FakeEngine:
        def __init__(self, weekly_amount, interval_days):
            self.weekly_amount = weekly_amount
            self.interval_days = interval_days

        def run(self, series, strategy, since):
            return f"drawdown-{self.interval_days}"

    monkeypatch.setattr(run_backtest, "BacktestEngine", FakeEngine)
    monkeypatch.setattr(run_backtest, "build_ma_independent_strategies", lambda weekly_amount: ["drawdown"])

    results = run_backtest.run_experiment_matrix(
        symbols=["BTC-USD"],
        since_dates=[datetime(2021, 1, 1, tzinfo=UTC)],
        weekly_amount="100",
        ma_windows=[20, 50],
        interval_days_options=[1, 3],
        data_root="data-root",
    )

    assert results == [
        "fixed-BTC-USD-2021-01-01-1",
        "trend-20-1",
        "dip-20-1",
        "trend-50-1",
        "dip-50-1",
        "drawdown-1",
        "fixed-BTC-USD-2021-01-01-3",
        "trend-20-3",
        "dip-20-3",
        "trend-50-3",
        "dip-50-3",
        "drawdown-3",
    ]
    assert calls == [
        ("BTC-USD", datetime(2021, 1, 1, tzinfo=UTC), "100", 20, 1, "data-root"),
        ("BTC-USD", datetime(2021, 1, 1, tzinfo=UTC), "100", 20, 1, "data-root"),
        ("BTC-USD", datetime(2021, 1, 1, tzinfo=UTC), "100", 50, 1, "data-root"),
        ("BTC-USD", datetime(2021, 1, 1, tzinfo=UTC), "100", 20, 3, "data-root"),
        ("BTC-USD", datetime(2021, 1, 1, tzinfo=UTC), "100", 20, 3, "data-root"),
        ("BTC-USD", datetime(2021, 1, 1, tzinfo=UTC), "100", 50, 3, "data-root"),
    ]


def test_save_results_creates_manifest_and_latest_snapshot(tmp_path):
    results = ["result"]
    monkey_manifest = {"hello": "world"}

    def fake_write_csv(path, saved_results):
        Path(path).write_text("csv")

    def fake_write_markdown(path, saved_results):
        Path(path).write_text("md")

    original_csv = run_backtest.write_results_csv
    original_markdown = run_backtest.write_results_markdown
    original_manifest = run_backtest.write_manifest_json
    original_table = run_backtest.format_results_table
    try:
        run_backtest.write_results_csv = fake_write_csv
        run_backtest.write_results_markdown = fake_write_markdown
        run_backtest.write_manifest_json = lambda path, manifest: Path(path).write_text(json.dumps(manifest))
        run_backtest.format_results_table = lambda saved_results: "txt"

        saved_paths = run_backtest.save_results(tmp_path, results, monkey_manifest, run_id="run-1")
    finally:
        run_backtest.write_results_csv = original_csv
        run_backtest.write_results_markdown = original_markdown
        run_backtest.write_manifest_json = original_manifest
        run_backtest.format_results_table = original_table

    assert (tmp_path / "run-1" / "manifest.json").exists()
    assert (tmp_path / "latest" / "manifest.json").exists()
    assert saved_paths["run_dir"] == tmp_path / "run-1"
