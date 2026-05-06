from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

from backtesting.engine import EquityPoint
from backtesting.portfolio_engine import PortfolioAllocationPoint
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
    allocation_curve: list


def make_fake_result(strategy_name="s1", start="2020-01-01", interval="7d"):
    points = [
        EquityPoint(datetime(2020, 1, 1, tzinfo=UTC), Decimal("100"), Decimal("10"), Decimal("0")),
        EquityPoint(datetime(2020, 1, 2, tzinfo=UTC), Decimal("120"), Decimal("8"), Decimal("0")),
    ]
    allocation_points = [
        PortfolioAllocationPoint(
            timestamp=datetime(2020, 1, 1, tzinfo=UTC),
            dai_units=Decimal("20"),
            btc_units=Decimal("0.1"),
            eth_units=Decimal("1.2"),
            dai_value=Decimal("20"),
            btc_value=Decimal("50"),
            eth_value=Decimal("30"),
            total_value=Decimal("100"),
            decision_reason="static_target_rebalance",
            action="buy_btc+buy_eth",
        ),
        PortfolioAllocationPoint(
            timestamp=datetime(2020, 1, 2, tzinfo=UTC),
            dai_units=Decimal("18"),
            btc_units=Decimal("0.1"),
            eth_units=Decimal("1.2"),
            dai_value=Decimal("18"),
            btc_value=Decimal("60"),
            eth_value=Decimal("42"),
            total_value=Decimal("120"),
            decision_reason="hold",
            action="hold",
        ),
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
        allocation_curve=allocation_points,
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
    monkeypatch.setattr(run_portfolio_backtest, "write_top_weekly_strategy_plots", lambda results, output_dir: [Path("c.svg")])
    monkeypatch.setattr(run_portfolio_backtest, "write_top_weekly_strategy_summary", lambda results, output_path: Path("summary.md"))
    monkeypatch.setattr(run_portfolio_backtest, "write_strategy_catalog", lambda results, output_path: Path("catalog.md"))
    monkeypatch.setattr(run_portfolio_backtest, "write_negative_window_summary", lambda results, output_path: Path("negative.md"))
    monkeypatch.setattr(run_portfolio_backtest, "copy_outputs_to_latest", lambda paths, latest_dir: None)
    monkeypatch.setattr(run_portfolio_backtest, "format_results_table", lambda results: "portfolio-table")
    monkeypatch.setattr(run_portfolio_backtest, "format_top_weekly_strategy_summary", lambda results: "weekly-summary")

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
            "--max-buy-trade-dai",
            "500",
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
        "max_buy_trade_dai": "500",
    }
    output = capsys.readouterr().out
    assert "portfolio-table" in output
    assert "weekly-summary" in output
    assert "Saved equity curve plots: 2" in output
    assert "Saved weekly top strategy plots: 1" in output
    assert "Saved strategy catalog:" in output
    assert "Saved negative-window summary:" in output


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


def test_rank_top_weekly_strategies_prefers_highest_mean_return():
    results = [
        make_fake_result(strategy_name="a", start="2020-01-01", interval="7d"),
        make_fake_result(strategy_name="a", start="2021-01-01", interval="7d"),
        make_fake_result(strategy_name="b", start="2020-01-01", interval="7d"),
        make_fake_result(strategy_name="c", start="2020-01-01", interval="5d"),
    ]
    results[0] = dataclass_replace(results[0], total_return_pct=Decimal("30"))
    results[1] = dataclass_replace(results[1], total_return_pct=Decimal("10"))
    results[2] = dataclass_replace(results[2], total_return_pct=Decimal("15"))

    ranking = run_portfolio_backtest.rank_top_weekly_strategies(results, limit=2)

    assert [row["strategy_name"] for row in ranking] == ["a", "b"]


def test_build_quarterly_since_dates_advances_in_3_month_steps():
    class FakeBundle:
        def common_timestamps_since(self, since):
            return [
                datetime(2020, 1, 1, tzinfo=UTC),
                datetime(2020, 1, 2, tzinfo=UTC),
                datetime(2021, 1, 15, tzinfo=UTC),
            ]

    since_dates = run_portfolio_backtest.build_quarterly_since_dates(FakeBundle(), start=datetime(2020, 1, 1, tzinfo=UTC))

    assert since_dates[:4] == [
        datetime(2020, 1, 1, tzinfo=UTC),
        datetime(2020, 4, 1, tzinfo=UTC),
        datetime(2020, 7, 1, tzinfo=UTC),
        datetime(2020, 10, 1, tzinfo=UTC),
    ]
    assert since_dates[-1] == datetime(2020, 10, 1, tzinfo=UTC)


def test_strategy_catalog_marks_negative_windows():
    result = dataclass_replace(make_fake_result(), total_return_pct=Decimal("-5"))

    markdown = run_portfolio_backtest.format_strategy_catalog([result])
    negative_summary = run_portfolio_backtest.format_negative_window_summary([result])

    assert "Annualized %" in markdown
    assert "yes" in markdown
    assert "2020-01-01" in negative_summary


def test_write_top_weekly_strategy_plots_writes_top3_weekly_only(tmp_path):
    results = [
        dataclass_replace(make_fake_result(strategy_name="a", start="2020-01-01", interval="7d"), total_return_pct=Decimal("30")),
        dataclass_replace(make_fake_result(strategy_name="a", start="2021-01-01", interval="7d"), total_return_pct=Decimal("25")),
        dataclass_replace(make_fake_result(strategy_name="b", start="2020-01-01", interval="7d"), total_return_pct=Decimal("20")),
        dataclass_replace(make_fake_result(strategy_name="c", start="2020-01-01", interval="7d"), total_return_pct=Decimal("10")),
        dataclass_replace(make_fake_result(strategy_name="d", start="2020-01-01", interval="7d"), total_return_pct=Decimal("5")),
        dataclass_replace(make_fake_result(strategy_name="z", start="2020-01-01", interval="5d"), total_return_pct=Decimal("999")),
    ]

    written = run_portfolio_backtest.write_top_weekly_strategy_plots(results, tmp_path)

    assert len(written) == 4
    assert (tmp_path / "weekly_strategy_a_2020-01-01.svg").exists()
    assert (tmp_path / "weekly_strategy_b_2020-01-01.svg").exists()
    assert not (tmp_path / "weekly_strategy_d_2020-01-01.svg").exists()
    svg_text = (tmp_path / "weekly_strategy_a_2020-01-01.svg").read_text()
    assert "BTC weekly trade usd" in svg_text
    assert "ETH weekly trade usd" in svg_text


def dataclass_replace(result, **updates):
    values = result.__dict__.copy()
    values.update(updates)
    return FakeResult(**values)
