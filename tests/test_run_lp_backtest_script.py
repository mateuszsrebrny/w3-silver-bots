from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

from backtesting.engine import EquityPoint
from backtesting.lp_comparison import LPComparisonResult
from scripts import run_lp_backtest


UTC = timezone.utc


def make_result(strategy_name="lp", pair_name="wbtc-weth"):
    return LPComparisonResult(
        strategy_name=strategy_name,
        strategy_label=f"{strategy_name}-label",
        symbol="BTC-USD+ETH-USD",
        pair_name=pair_name,
        contribution_interval="1d",
        start_timestamp=datetime(2020, 1, 1, tzinfo=UTC),
        end_timestamp=datetime(2020, 1, 2, tzinfo=UTC),
        initial_value=Decimal("1000"),
        ending_value=Decimal("1200"),
        total_return_pct=Decimal("20"),
        max_drawdown_pct=Decimal("5"),
        fee_yield_pct=Decimal("26"),
        yield_mode="apr",
        equity_curve=[
            EquityPoint(datetime(2020, 1, 1, tzinfo=UTC), Decimal("1000"), Decimal("0"), Decimal("0")),
            EquityPoint(datetime(2020, 1, 2, tzinfo=UTC), Decimal("1200"), Decimal("0"), Decimal("0")),
        ],
    )


def test_parse_since_returns_utc_datetime():
    assert run_lp_backtest.parse_since("2020-01-01") == datetime(2020, 1, 1, tzinfo=UTC)


def test_main_passes_arguments_to_runner(monkeypatch, capsys):
    captured = {}

    def fake_run_lp_comparison_matrix(pairs, since_dates, initial_value, yield_mode, data_root, pair_yields):
        captured["pairs"] = pairs
        captured["since_dates"] = since_dates
        captured["initial_value"] = initial_value
        captured["yield_mode"] = yield_mode
        captured["data_root"] = data_root
        captured["pair_yields"] = pair_yields
        return [make_result()]

    monkeypatch.setattr(run_lp_backtest, "run_lp_comparison_matrix", fake_run_lp_comparison_matrix)
    monkeypatch.setattr(
        run_lp_backtest,
        "save_results",
        lambda output_dir, results, manifest: {
            "manifest": f"{output_dir}/manifest.json",
        },
    )
    monkeypatch.setattr(run_lp_backtest, "format_results_table", lambda results: "lp-table")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_lp_backtest.py",
            "--pair",
            "wbtc-weth",
            "--pair",
            "usdt-weth",
            "--since",
            "2021-01-01",
            "--initial-value",
            "25000",
            "--yield-mode",
            "apy",
            "--wbtc-weth-yield-pct",
            "26",
            "--usdt-weth-yield-pct",
            "45",
            "--data-root",
            "custom-data",
            "--output-dir",
            "custom-reports",
        ],
    )

    run_lp_backtest.main()

    assert captured == {
        "pairs": ["wbtc-weth", "usdt-weth"],
        "since_dates": [datetime(2021, 1, 1, tzinfo=UTC)],
        "initial_value": "25000",
        "yield_mode": "apy",
        "data_root": "custom-data",
        "pair_yields": {"wbtc-weth": "26", "usdt-weth": "45"},
    }
    output = capsys.readouterr().out
    assert "lp-table" in output
    assert "Saved Manifest: custom-reports/manifest.json" in output


def test_save_results_creates_manifest_and_latest_snapshot(tmp_path):
    result = make_result()
    saved_paths = run_lp_backtest.save_results(tmp_path, [result], {"hello": "world"}, run_id="run-1")

    assert (tmp_path / "run-1" / "manifest.json").exists()
    assert (tmp_path / "run-1" / "break_even_summary.md").exists()
    assert (tmp_path / "latest" / "manifest.json").exists()
    assert saved_paths["run_dir"] == tmp_path / "run-1"
