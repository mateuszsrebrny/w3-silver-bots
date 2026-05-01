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
