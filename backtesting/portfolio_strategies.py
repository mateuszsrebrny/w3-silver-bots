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


class NarrowCashBandRebalance:
    name = "narrow_cash_band_rebalance"

    def __init__(
        self,
        ma_window_days=200,
        drawdown_window_days=365,
        bear_cash_weight="0.10",
        neutral_cash_weight="0.20",
        bull_cash_weight="0.35",
        rebalance_fraction="0.40",
        cheap_asset_tilt="0.10",
    ):
        self.ma_window_days = ma_window_days
        self.drawdown_window_days = drawdown_window_days
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

        if btc["cheap"] and eth["cheap"]:
            cash_weight = self.bear_cash_weight
            reason = "both_assets_cheap"
        elif btc["expensive"] and eth["expensive"]:
            cash_weight = self.bull_cash_weight
            reason = "both_assets_expensive"
        else:
            cash_weight = self.neutral_cash_weight
            reason = "mixed_regime"

        return _balanced_weights(
            cash_weight,
            self.rebalance_fraction,
            reason,
            btc,
            eth,
            self.cheap_asset_tilt,
        )

    def label(self):
        return (
            f"{self.name}(ma_window_days={self.ma_window_days},"
            f"drawdown_window_days={self.drawdown_window_days},"
            f"bear_cash_weight={self.bear_cash_weight},"
            f"neutral_cash_weight={self.neutral_cash_weight},"
            f"bull_cash_weight={self.bull_cash_weight})"
        )


class DrawdownTiltRebalance:
    name = "drawdown_tilt_rebalance"

    def __init__(
        self,
        drawdown_window_days=365,
        deep_drawdown="0.50",
        medium_drawdown="0.25",
        deep_bear_cash_weight="0.05",
        bear_cash_weight="0.15",
        neutral_cash_weight="0.25",
        bull_cash_weight="0.40",
        rebalance_fraction="0.45",
        max_asset_tilt="0.20",
    ):
        self.drawdown_window_days = drawdown_window_days
        self.deep_drawdown = Decimal(str(deep_drawdown))
        self.medium_drawdown = Decimal(str(medium_drawdown))
        self.deep_bear_cash_weight = Decimal(str(deep_bear_cash_weight))
        self.bear_cash_weight = Decimal(str(bear_cash_weight))
        self.neutral_cash_weight = Decimal(str(neutral_cash_weight))
        self.bull_cash_weight = Decimal(str(bull_cash_weight))
        self.rebalance_fraction = Decimal(str(rebalance_fraction))
        self.max_asset_tilt = Decimal(str(max_asset_tilt))

    def decide(self, timestamp, bundle, state):
        btc = _asset_signal(bundle, "BTC-USD", timestamp, 200, self.drawdown_window_days)
        eth = _asset_signal(bundle, "ETH-USD", timestamp, 200, self.drawdown_window_days)

        if btc is None or eth is None:
            return Static50_50Rebalance(
                cash_weight=self.neutral_cash_weight,
                rebalance_fraction=self.rebalance_fraction,
            ).decide(timestamp, bundle, state)

        deepest_drawdown = max(btc["drawdown"], eth["drawdown"])
        if deepest_drawdown >= self.deep_drawdown:
            cash_weight = self.deep_bear_cash_weight
            reason = "deep_drawdown"
        elif deepest_drawdown >= self.medium_drawdown:
            cash_weight = self.bear_cash_weight
            reason = "medium_drawdown"
        elif btc["expensive"] and eth["expensive"]:
            cash_weight = self.bull_cash_weight
            reason = "both_assets_expensive"
        else:
            cash_weight = self.neutral_cash_weight
            reason = "neutral_drawdown"

        tilt = _drawdown_tilt(btc["drawdown"], eth["drawdown"], self.max_asset_tilt)
        btc_risk_share = HALF
        if btc["drawdown"] > eth["drawdown"]:
            btc_risk_share += tilt
            reason += "_btc_tilt"
        elif eth["drawdown"] > btc["drawdown"]:
            btc_risk_share -= tilt
            reason += "_eth_tilt"

        return _manual_weights(
            cash_weight=cash_weight,
            btc_risk_share=btc_risk_share,
            rebalance_fraction=self.rebalance_fraction,
            reason=reason,
        )

    def label(self):
        return (
            f"{self.name}(drawdown_window_days={self.drawdown_window_days},"
            f"deep_drawdown={self.deep_drawdown},"
            f"medium_drawdown={self.medium_drawdown},"
            f"deep_bear_cash_weight={self.deep_bear_cash_weight},"
            f"bull_cash_weight={self.bull_cash_weight})"
        )


class BTCDefensiveETHAggressive:
    name = "btc_defensive_eth_aggressive"

    def __init__(
        self,
        ma_window_days=200,
        return_window_days=84,
        weak_cash_weight="0.25",
        neutral_cash_weight="0.15",
        strong_cash_weight="0.10",
        eth_overweight="0.15",
        btc_overweight="0.10",
        rebalance_fraction="0.40",
    ):
        self.ma_window_days = ma_window_days
        self.return_window_days = return_window_days
        self.weak_cash_weight = Decimal(str(weak_cash_weight))
        self.neutral_cash_weight = Decimal(str(neutral_cash_weight))
        self.strong_cash_weight = Decimal(str(strong_cash_weight))
        self.eth_overweight = Decimal(str(eth_overweight))
        self.btc_overweight = Decimal(str(btc_overweight))
        self.rebalance_fraction = Decimal(str(rebalance_fraction))

    def decide(self, timestamp, bundle, state):
        btc = _asset_signal(bundle, "BTC-USD", timestamp, self.ma_window_days, 365)
        eth = _asset_signal(bundle, "ETH-USD", timestamp, self.ma_window_days, 365)

        if btc is None or eth is None:
            return Static50_50Rebalance(
                cash_weight=self.neutral_cash_weight,
                rebalance_fraction=self.rebalance_fraction,
            ).decide(timestamp, bundle, state)

        btc_return = bundle.trailing_return("BTC-USD", timestamp, self.return_window_days)
        eth_return = bundle.trailing_return("ETH-USD", timestamp, self.return_window_days)
        if btc_return is None or eth_return is None:
            return Static50_50Rebalance(
                cash_weight=self.neutral_cash_weight,
                rebalance_fraction=self.rebalance_fraction,
            ).decide(timestamp, bundle, state)

        btc_strong = not btc["cheap"]
        eth_strong = not eth["cheap"] and eth_return > btc_return

        if btc["cheap"] and eth["cheap"]:
            cash_weight = self.weak_cash_weight
            reason = "both_weak_btc_defensive"
            return _manual_weights(
                cash_weight=cash_weight,
                btc_risk_share=Decimal("0.60"),
                rebalance_fraction=self.rebalance_fraction,
                reason=reason,
            )

        if eth_strong and not btc["expensive"]:
            cash_weight = self.strong_cash_weight
            reason = "eth_strong_risk_on"
            return _manual_weights(
                cash_weight=cash_weight,
                btc_risk_share=HALF - self.eth_overweight,
                rebalance_fraction=self.rebalance_fraction,
                reason=reason,
            )

        if btc_strong and not eth_strong:
            cash_weight = self.neutral_cash_weight
            reason = "btc_defensive_regime"
            return _manual_weights(
                cash_weight=cash_weight,
                btc_risk_share=HALF + self.btc_overweight,
                rebalance_fraction=self.rebalance_fraction,
                reason=reason,
            )

        return _manual_weights(
            cash_weight=self.neutral_cash_weight,
            btc_risk_share=HALF,
            rebalance_fraction=self.rebalance_fraction,
            reason="balanced_regime",
        )

    def label(self):
        return (
            f"{self.name}(ma_window_days={self.ma_window_days},"
            f"return_window_days={self.return_window_days},"
            f"weak_cash_weight={self.weak_cash_weight},"
            f"neutral_cash_weight={self.neutral_cash_weight},"
            f"strong_cash_weight={self.strong_cash_weight})"
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


def _balanced_weights(cash_weight, rebalance_fraction, reason, btc, eth, cheap_asset_tilt):
    risk_weight = ONE - cash_weight
    btc_weight = risk_weight * HALF
    eth_weight = risk_weight * HALF

    if btc["cheap"] and not eth["cheap"]:
        btc_weight += risk_weight * cheap_asset_tilt
        eth_weight -= risk_weight * cheap_asset_tilt
        reason += "_btc_tilt"
    elif eth["cheap"] and not btc["cheap"]:
        eth_weight += risk_weight * cheap_asset_tilt
        btc_weight -= risk_weight * cheap_asset_tilt
        reason += "_eth_tilt"

    return TargetAllocationDecision(
        target_weights={
            "BTC-USD": btc_weight,
            "ETH-USD": eth_weight,
            "DAI": cash_weight,
        },
        rebalance_fraction=rebalance_fraction,
        reason=reason,
    )


def _manual_weights(cash_weight, btc_risk_share, rebalance_fraction, reason):
    risk_weight = ONE - cash_weight
    btc_weight = risk_weight * btc_risk_share
    eth_weight = risk_weight - btc_weight
    return TargetAllocationDecision(
        target_weights={
            "BTC-USD": btc_weight,
            "ETH-USD": eth_weight,
            "DAI": cash_weight,
        },
        rebalance_fraction=rebalance_fraction,
        reason=reason,
    )


def _drawdown_tilt(btc_drawdown, eth_drawdown, max_asset_tilt):
    if btc_drawdown == eth_drawdown:
        return Decimal("0")

    drawdown_gap = abs(btc_drawdown - eth_drawdown)
    scaled_tilt = min(max_asset_tilt, drawdown_gap / Decimal("2"))
    return scaled_tilt
