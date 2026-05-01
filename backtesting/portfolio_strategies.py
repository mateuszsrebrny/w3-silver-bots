from dataclasses import dataclass
from decimal import Decimal


ONE = Decimal("1")
HALF = Decimal("0.5")


@dataclass(frozen=True)
class TargetAllocationDecision:
    target_weights: dict
    rebalance_fraction: Decimal
    reason: str


class Static50_50Rebalance:
    name = "static_50_50_rebalance"

    def __init__(self, cash_weight="0.20", rebalance_fraction="0.50"):
        self.cash_weight = Decimal(str(cash_weight))
        self.rebalance_fraction = Decimal(str(rebalance_fraction))

    def decide(self, timestamp, bundle, state):
        risk_weight = ONE - self.cash_weight
        return TargetAllocationDecision(
            target_weights={
                "BTC-USD": risk_weight * HALF,
                "ETH-USD": risk_weight * HALF,
                "DAI": self.cash_weight,
            },
            rebalance_fraction=self.rebalance_fraction,
            reason="static_target_rebalance",
        )

    def label(self):
        return (
            f"{self.name}(cash_weight={self.cash_weight},"
            f"rebalance_fraction={self.rebalance_fraction})"
        )


class Target50_50WithCashBand:
    name = "target_50_50_with_cash_band"

    def __init__(
        self,
        ma_window_days=200,
        drawdown_window_days=365,
        cheap_drawdown="0.35",
        expensive_drawdown="0.15",
        bear_cash_weight="0.10",
        neutral_cash_weight="0.30",
        bull_cash_weight="0.60",
        rebalance_fraction="0.50",
        cheap_asset_tilt="0.10",
    ):
        self.ma_window_days = ma_window_days
        self.drawdown_window_days = drawdown_window_days
        self.cheap_drawdown = Decimal(str(cheap_drawdown))
        self.expensive_drawdown = Decimal(str(expensive_drawdown))
        self.bear_cash_weight = Decimal(str(bear_cash_weight))
        self.neutral_cash_weight = Decimal(str(neutral_cash_weight))
        self.bull_cash_weight = Decimal(str(bull_cash_weight))
        self.rebalance_fraction = Decimal(str(rebalance_fraction))
        self.cheap_asset_tilt = Decimal(str(cheap_asset_tilt))

    def decide(self, timestamp, bundle, state):
        btc = _asset_signal(bundle, "BTC-USD", timestamp, self.ma_window_days, self.drawdown_window_days)
        eth = _asset_signal(bundle, "ETH-USD", timestamp, self.ma_window_days, self.drawdown_window_days)

        if btc is None or eth is None:
            return Static50_50Rebalance(
                cash_weight=self.neutral_cash_weight,
                rebalance_fraction=self.rebalance_fraction,
            ).decide(timestamp, bundle, state)

        cheap_assets = [signal for signal in [btc, eth] if signal["cheap"]]
        expensive_assets = [signal for signal in [btc, eth] if signal["expensive"]]

        if len(cheap_assets) == 2:
            cash_weight = self.bear_cash_weight
            reason = "both_assets_cheap"
        elif len(expensive_assets) == 2:
            cash_weight = self.bull_cash_weight
            reason = "both_assets_expensive"
        elif cheap_assets:
            cash_weight = (self.bear_cash_weight + self.neutral_cash_weight) / Decimal("2")
            reason = "one_asset_cheap"
        elif expensive_assets:
            cash_weight = (self.neutral_cash_weight + self.bull_cash_weight) / Decimal("2")
            reason = "one_asset_expensive"
        else:
            cash_weight = self.neutral_cash_weight
            reason = "neutral_regime"

        risk_weight = ONE - cash_weight
        btc_weight = risk_weight * HALF
        eth_weight = risk_weight * HALF

        if btc["cheap"] and not eth["cheap"]:
            btc_weight += risk_weight * self.cheap_asset_tilt
            eth_weight -= risk_weight * self.cheap_asset_tilt
            reason += "_btc_tilt"
        elif eth["cheap"] and not btc["cheap"]:
            eth_weight += risk_weight * self.cheap_asset_tilt
            btc_weight -= risk_weight * self.cheap_asset_tilt
            reason += "_eth_tilt"

        return TargetAllocationDecision(
            target_weights={
                "BTC-USD": btc_weight,
                "ETH-USD": eth_weight,
                "DAI": cash_weight,
            },
            rebalance_fraction=self.rebalance_fraction,
            reason=reason,
        )

    def label(self):
        return (
            f"{self.name}(ma_window_days={self.ma_window_days},"
            f"drawdown_window_days={self.drawdown_window_days},"
            f"bear_cash_weight={self.bear_cash_weight},"
            f"neutral_cash_weight={self.neutral_cash_weight},"
            f"bull_cash_weight={self.bull_cash_weight})"
        )


def _asset_signal(bundle, symbol, timestamp, ma_window_days, drawdown_window_days):
    close = bundle.close(symbol, timestamp)
    moving_average = bundle.moving_average(symbol, timestamp, ma_window_days)
    drawdown = bundle.drawdown_from_high(symbol, timestamp, drawdown_window_days)
    if close is None or moving_average is None or drawdown is None:
        return None

    cheap = close < moving_average or drawdown >= Decimal("0.35")
    expensive = close > moving_average and drawdown <= Decimal("0.15")

    return {
        "symbol": symbol,
        "close": close,
        "moving_average": moving_average,
        "drawdown": drawdown,
        "cheap": cheap,
        "expensive": expensive,
    }
