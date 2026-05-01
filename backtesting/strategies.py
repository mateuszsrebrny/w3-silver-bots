from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Decision:
    buy_usd: Decimal
    reason: str


class WeeklyFixedDCA:
    name = "weekly_fixed_dca"

    def __init__(self, weekly_amount_usd):
        self.weekly_amount_usd = Decimal(str(weekly_amount_usd))

    def decide(self, candle, series, state):
        return Decision(self.weekly_amount_usd, "scheduled buy")

    def label(self):
        return f"{self.name}(weekly_amount_usd={self.weekly_amount_usd})"


class WeeklyMATrendDCA:
    name = "weekly_ma_trend_dca"

    def __init__(self, weekly_amount_usd, window_days=50):
        self.weekly_amount_usd = Decimal(str(weekly_amount_usd))
        self.window_days = window_days

    def decide(self, candle, series, state):
        moving_average = series.moving_average(candle.timestamp, self.window_days)
        if moving_average is None:
            return Decision(Decimal("0"), "insufficient_ma_history")
        if candle.close > moving_average:
            return Decision(self.weekly_amount_usd, "price_above_ma")
        return Decision(Decimal("0"), "price_not_above_ma")

    def label(self):
        return (
            f"{self.name}(weekly_amount_usd={self.weekly_amount_usd},"
            f"window_days={self.window_days})"
        )


class WeeklyDipDCA:
    name = "weekly_dip_dca"

    def __init__(self, weekly_amount_usd, window_days=50):
        self.weekly_amount_usd = Decimal(str(weekly_amount_usd))
        self.window_days = window_days

    def decide(self, candle, series, state):
        moving_average = series.moving_average(candle.timestamp, self.window_days)
        if moving_average is None:
            return Decision(Decimal("0"), "insufficient_ma_history")
        if candle.close < moving_average:
            return Decision(self.weekly_amount_usd, "price_below_ma")
        return Decision(Decimal("0"), "price_not_below_ma")

    def label(self):
        return (
            f"{self.name}(weekly_amount_usd={self.weekly_amount_usd},"
            f"window_days={self.window_days})"
        )


class WeeklyMAScaledDCA:
    name = "weekly_ma_scaled_dca"

    def __init__(
        self,
        weekly_amount_usd,
        window_days=50,
        below_multiplier="2.0",
        above_multiplier="0.5",
    ):
        self.weekly_amount_usd = Decimal(str(weekly_amount_usd))
        self.window_days = window_days
        self.below_multiplier = Decimal(str(below_multiplier))
        self.above_multiplier = Decimal(str(above_multiplier))

    def decide(self, candle, series, state):
        moving_average = series.moving_average(candle.timestamp, self.window_days)
        if moving_average is None:
            return Decision(self.weekly_amount_usd, "insufficient_ma_history_default_buy")
        if candle.close < moving_average:
            return Decision(self.weekly_amount_usd * self.below_multiplier, "price_below_ma_scaled_up")
        return Decision(self.weekly_amount_usd * self.above_multiplier, "price_above_ma_scaled_down")

    def label(self):
        return (
            f"{self.name}(weekly_amount_usd={self.weekly_amount_usd},"
            f"window_days={self.window_days},below_multiplier={self.below_multiplier},"
            f"above_multiplier={self.above_multiplier})"
        )


class WeeklyDrawdownScaledDCA:
    name = "weekly_drawdown_scaled_dca"

    def __init__(
        self,
        weekly_amount_usd,
        lookback_days=90,
        mild_drawdown_pct="0.10",
        deep_drawdown_pct="0.20",
        mild_multiplier="1.5",
        deep_multiplier="2.0",
        high_multiplier="0.5",
    ):
        self.weekly_amount_usd = Decimal(str(weekly_amount_usd))
        self.lookback_days = lookback_days
        self.mild_drawdown_pct = Decimal(str(mild_drawdown_pct))
        self.deep_drawdown_pct = Decimal(str(deep_drawdown_pct))
        self.mild_multiplier = Decimal(str(mild_multiplier))
        self.deep_multiplier = Decimal(str(deep_multiplier))
        self.high_multiplier = Decimal(str(high_multiplier))

    def decide(self, candle, series, state):
        drawdown = series.drawdown_from_high(candle.timestamp, self.lookback_days)
        if drawdown is None:
            return Decision(self.weekly_amount_usd, "insufficient_drawdown_history_default_buy")
        if drawdown >= self.deep_drawdown_pct:
            return Decision(self.weekly_amount_usd * self.deep_multiplier, "deep_drawdown_scaled_up")
        if drawdown >= self.mild_drawdown_pct:
            return Decision(self.weekly_amount_usd * self.mild_multiplier, "mild_drawdown_scaled_up")
        return Decision(self.weekly_amount_usd * self.high_multiplier, "near_high_scaled_down")

    def label(self):
        return (
            f"{self.name}(weekly_amount_usd={self.weekly_amount_usd},"
            f"lookback_days={self.lookback_days},mild_drawdown_pct={self.mild_drawdown_pct},"
            f"deep_drawdown_pct={self.deep_drawdown_pct})"
        )
