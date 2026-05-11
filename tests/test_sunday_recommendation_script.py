from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import sys

from backtesting.portfolio_engine import PortfolioAllocationPoint, PortfolioDecisionSnapshot
from backtesting.portfolio_strategies import TargetAllocationDecision
from scripts import sunday_recommendation


UTC = timezone.utc


class FakeBundle:
    def __init__(self):
        self.timestamps = [
            datetime(2026, 5, 9, tzinfo=UTC),
        ]

    def common_timestamps_since(self, since):
        return [timestamp for timestamp in self.timestamps if timestamp >= since]

    def close(self, symbol, timestamp):
        return {
            "BTC-USD": Decimal("80000"),
            "ETH-USD": Decimal("2400"),
        }[symbol]

    def moving_average(self, symbol, timestamp, window_days):
        return {
            "BTC-USD": Decimal("90000"),
            "ETH-USD": Decimal("2600"),
        }[symbol]

    def drawdown_from_high(self, symbol, timestamp, window_days):
        return {
            "BTC-USD": Decimal("0.20"),
            "ETH-USD": Decimal("0.35"),
        }[symbol]

    def trailing_return(self, symbol, timestamp, window_days):
        return {
            "BTC-USD": Decimal("0.08"),
            "ETH-USD": Decimal("0.02"),
        }[symbol]


@dataclass(frozen=True)
class FakeStrategy:
    name: str = "budgeted_btc_defensive_eth_aggressive"

    def label(self):
        return f"{self.name}()"


def test_main_prints_compact_recommendation(monkeypatch, capsys):
    timestamp = datetime(2026, 5, 9, tzinfo=UTC)
    snapshot = PortfolioDecisionSnapshot(
        timestamp=timestamp,
        decision=TargetAllocationDecision(
            target_weights={
                "BTC-USD": Decimal("0.45"),
                "ETH-USD": Decimal("0.30"),
                "DAI": Decimal("0.25"),
            },
            rebalance_fraction=Decimal("0.40"),
            reason="both_weak_btc_defensive",
        ),
        current_weights={
            "BTC-USD": Decimal("0.25"),
            "ETH-USD": Decimal("0.30"),
            "DAI": Decimal("0.45"),
        },
        target_weights={
            "BTC-USD": Decimal("0.45"),
            "ETH-USD": Decimal("0.30"),
            "DAI": Decimal("0.25"),
        },
        current_values={
            "BTC-USD": Decimal("5600"),
            "ETH-USD": Decimal("7200"),
        },
        total_value=Decimal("22800"),
        trades=[],
        allocation_point=PortfolioAllocationPoint(
            timestamp=timestamp,
            dai_units=Decimal("9550"),
            btc_units=Decimal("0.075625"),
            eth_units=Decimal("3"),
            dai_value=Decimal("9550"),
            btc_value=Decimal("6050"),
            eth_value=Decimal("7200"),
            total_value=Decimal("22800"),
            decision_reason="both_weak_btc_defensive",
            action="buy_btc",
        ),
    )

    monkeypatch.setattr(sunday_recommendation, "build_bundle", lambda data_root: FakeBundle())
    monkeypatch.setattr(sunday_recommendation, "find_effective_timestamp", lambda bundle, requested: timestamp)
    monkeypatch.setattr(
        sunday_recommendation,
        "dry_run",
        lambda **kwargs: [(FakeStrategy(), snapshot)],
    )
    monkeypatch.setattr(
        sunday_recommendation,
        "_signed_trade_notional",
        lambda snapshot, symbol: Decimal("450") if symbol == "BTC-USD" else Decimal("0"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sunday_recommendation.py",
            "--date",
            "2026-05-10",
            "--dai",
            "10000",
            "--btc",
            "0.07",
            "--eth",
            "3",
        ],
    )

    sunday_recommendation.main()

    output = capsys.readouterr().out
    assert "Strategy: budgeted_btc_defensive_eth_aggressive" in output
    assert "Reason: both_weak_btc_defensive" in output
    assert "Action: buy_btc" in output
    assert "- BTC: 450.00 USD" in output
    assert "- ETH: 0.00 USD" in output
    assert "Signal diagnostics:" in output
    assert "Relative returns (84d): BTC 8.00%, ETH 2.00%" in output
    assert "Both BTC and ETH are still in the strategy's cheap/weak bucket." in output
