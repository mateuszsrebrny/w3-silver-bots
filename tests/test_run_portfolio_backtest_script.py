from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

from backtesting.engine import EquityPoint
from scripts import run_portfolio_backtest


UTC = timezone.utc


@dataclass(frozen=True)
class FakeResult:
    strategy_name: str
    strategy_label: str
    symbol: str
    contribution_interval: str
    start_timestamp: datetime
    end_timestamp: datetime
    initial_value: Decimal
    gross_buys_dai: Decimal
    gross_sells_dai: Decimal
    net_buys_dai: Decimal
    ending_dai: Decimal
    ending_btc_units: Decimal
    ending_eth_units: Decimal
    ending_value: Decimal
    total_withdrawn_dai: Decimal
    realized_value: Decimal
    total_return_pct: Decimal
    turnover_pct: Decimal
    max_drawdown_pct: Decimal
    trade_count: int
    trades: list
    equity_curve: list


def make_fake_result(strategy_name="s1", start="2020-01-01", interval="7d"):
    points = [
        EquityPoint(datetime(2020, 1, 1, tzinfo=UTC), Decimal("100"), Decimal("10"), Decimal("0")),
        EquityPoint(datetime(2020, 1, 2, tzinfo=UTC), Decimal("120"), Decimal("8"), Decimal("0")),
    ]
    return FakeResult(
        strategy_name=strategy_name,
        strategy_label=f"{strategy_name}-label",
        symbol="BTC-USD+ETH-USD+DAI",
        contribution_interval=interval,
        start_timestamp=datetime.fromisoformat(start).replace(tzinfo=UTC),
        end_timestamp=datetime(2020, 1, 2, tzinfo=UTC),
        initial_value=Decimal("100"),
        gross_buys_dai=Decimal("10"),
        gross_sells_dai=Decimal("5"),
        net_buys_dai=Decimal("5"),
        ending_dai=Decimal("20"),
        ending_btc_units=Decimal("0.1"),
        ending_eth_units=Decimal("1.2"),
        ending_value=Decimal("120"),
        total_withdrawn_dai=Decimal("0"),
        realized_value=Decimal("120"),
        total_return_pct=Decimal("20"),
        turnover_pct=Decimal("15"),
        max_drawdown_pct=Decimal("5"),
        trade_count=2,
        trades=[],
        equity_curve=points,
    )


def test_parse_since_returns_utc_datetime():
    assert run_portfolio_backtest.parse_since("2020-01-01") == datetime(2020, 1, 1, tzinfo=UTC)


def test_main_passes_arguments_and_reports_paths(monkeypatch, capsys):
    captured = {}

    monkeypatch.setattr(run_portfolio_backtest, "build_bundle", lambda data_root: "bundle")

    def fake_run_portfolio_backtests(**kwargs):
        captured.update(kwargs)
        return [make_fake_result()]

    monkeypatch.setattr(run_portfolio_backtest, "run_portfolio_backtests", fake_run_portfolio_backtests)
    monkeypatch.setattr(
        run_portfolio_backtest,
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
    monkeypatch.setattr(run_portfolio_backtest, "write_equity_curve_plots", lambda results, output_dir: [Path("a.svg"), Path("b.svg")])
    monkeypatch.setattr(run_portfolio_backtest, "copy_outputs_to_latest", lambda paths, latest_dir: None)
    monkeypatch.setattr(run_portfolio_backtest, "format_results_table", lambda results: "portfolio-table")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_portfolio_backtest.py",
            "--since",
            "2021-01-01",
            "--since",
            "2022-01-01",
            "--interval-days",
            "2",
            "--interval-days",
            "7",
            "--data-root",
            "custom-data",
            "--output-dir",
            "custom-reports",
            "--initial-btc",
            "1.5",
            "--initial-eth",
            "10",
            "--initial-dai",
            "5000",
            "--withdrawal-dai",
            "100",
            "--withdrawal-interval-days",
            "30",
        ],
    )

    run_portfolio_backtest.main()

    assert captured == {
        "bundle": "bundle",
        "since_dates": [
            datetime(2021, 1, 1, tzinfo=UTC),
            datetime(2022, 1, 1, tzinfo=UTC),
        ],
        "interval_days_options": [2, 7],
        "initial_btc": "1.5",
        "initial_eth": "10",
        "initial_dai": "5000",
        "withdrawal_dai": "100",
        "withdrawal_interval_days": 30,
    }
    output = capsys.readouterr().out
    assert "portfolio-table" in output
    assert "Saved equity curve plots: 2" in output


def test_save_results_creates_manifest_and_latest_snapshot(tmp_path):
    result = make_fake_result()
    saved_paths = run_portfolio_backtest.save_results(tmp_path, [result], {"hello": "world"}, run_id="run-1")

    assert (tmp_path / "run-1" / "manifest.json").exists()
    assert (tmp_path / "latest" / "manifest.json").exists()
    assert saved_paths["run_dir"] == tmp_path / "run-1"


def test_write_equity_curve_plots_writes_one_svg_per_scenario(tmp_path):
    results = [
        make_fake_result(strategy_name="s1", start="2020-01-01", interval="7d"),
        make_fake_result(strategy_name="s2", start="2020-01-01", interval="7d"),
        make_fake_result(strategy_name="s1", start="2021-01-01", interval="5d"),
    ]

    written = run_portfolio_backtest.write_equity_curve_plots(results, tmp_path)

    assert len(written) == 2
    assert (tmp_path / "portfolio_value_2020-01-01_7d.svg").exists()
    assert "Portfolio Value Over Time" in (tmp_path / "portfolio_value_2020-01-01_7d.svg").read_text()
