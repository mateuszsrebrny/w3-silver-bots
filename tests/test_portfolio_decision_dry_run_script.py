from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import sys

from backtesting.portfolio_engine import PortfolioAllocationPoint, PortfolioDecisionSnapshot
from backtesting.portfolio_strategies import TargetAllocationDecision
from scripts import portfolio_decision_dry_run


UTC = timezone.utc


class FakeBundle:
    def __init__(self):
        self.timestamps = [
            datetime(2026, 5, 3, tzinfo=UTC),
            datetime(2026, 5, 4, tzinfo=UTC),
        ]

    def common_timestamps_since(self, since):
        return [timestamp for timestamp in self.timestamps if timestamp >= since]

    def close(self, symbol, timestamp):
        return {
            "BTC-USD": Decimal("100000"),
            "ETH-USD": Decimal("2000"),
        }[symbol]


@dataclass(frozen=True)
class FakeStrategy:
    name: str = "fake_strategy"

    def label(self):
        return "fake_strategy()"


def test_find_effective_timestamp_uses_latest_on_or_before_date():
    bundle = FakeBundle()
    requested = datetime(2026, 5, 4, tzinfo=UTC)

    effective = portfolio_decision_dry_run.find_effective_timestamp(bundle, requested)

    assert effective == datetime(2026, 5, 4, tzinfo=UTC)


def test_find_effective_timestamp_falls_back_to_prior_available_date():
    bundle = FakeBundle()
    requested = datetime(2026, 5, 5, tzinfo=UTC)

    effective = portfolio_decision_dry_run.find_effective_timestamp(bundle, requested)

    assert effective == datetime(2026, 5, 4, tzinfo=UTC)


def test_main_prints_strategy_snapshot(monkeypatch, capsys):
    timestamp = datetime(2026, 5, 4, tzinfo=UTC)
    snapshot = PortfolioDecisionSnapshot(
        timestamp=timestamp,
        decision=TargetAllocationDecision(
            target_weights={
                "BTC-USD": Decimal("0.45"),
                "ETH-USD": Decimal("0.45"),
                "DAI": Decimal("0.10"),
            },
            rebalance_fraction=Decimal("0.50"),
            reason="both_assets_cheap",
        ),
        current_weights={
            "BTC-USD": Decimal("0"),
            "ETH-USD": Decimal("0"),
            "DAI": Decimal("1"),
        },
        target_weights={
            "BTC-USD": Decimal("0.45"),
            "ETH-USD": Decimal("0.45"),
            "DAI": Decimal("0.10"),
        },
        current_values={
            "BTC-USD": Decimal("0"),
            "ETH-USD": Decimal("0"),
        },
        total_value=Decimal("10000"),
        trades=[],
        allocation_point=PortfolioAllocationPoint(
            timestamp=timestamp,
            dai_units=Decimal("9100"),
            btc_units=Decimal("0.0045"),
            eth_units=Decimal("0.225"),
            dai_value=Decimal("9100"),
            btc_value=Decimal("450"),
            eth_value=Decimal("450"),
            total_value=Decimal("10000"),
            decision_reason="both_assets_cheap",
            action="hold",
        ),
    )

    monkeypatch.setattr(portfolio_decision_dry_run, "build_bundle", lambda data_root: FakeBundle())
    monkeypatch.setattr(portfolio_decision_dry_run, "find_effective_timestamp", lambda bundle, requested: timestamp)
    monkeypatch.setattr(
        portfolio_decision_dry_run,
        "dry_run",
        lambda **kwargs: [(FakeStrategy(), snapshot)],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "portfolio_decision_dry_run.py",
            "--date",
            "2026-05-05",
            "--dai",
            "10000",
            "--btc",
            "0",
            "--eth",
            "0",
            "--max-buy-trade-dai",
            "100",
        ],
    )

    portfolio_decision_dry_run.main()

    output = capsys.readouterr().out
    assert "Requested date: 2026-05-05" in output
    assert "Effective date: 2026-05-04" in output
    assert "fake_strategy" in output
    assert "both_assets_cheap" in output
    assert "BTC 45.00%, ETH 45.00%, DAI 10.00%" in output
