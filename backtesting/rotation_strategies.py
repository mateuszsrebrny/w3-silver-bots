from dataclasses import dataclass
from decimal import Decimal


ONE = Decimal("1")
HALF = Decimal("0.5")
ZERO = Decimal("0")


@dataclass(frozen=True)
class AllocationDecision:
    weights: dict
    reason: str


class BTCOnlyWeekly:
    name = "btc_only_weekly"

    def decide(self, timestamp, bundle, state):
        return AllocationDecision({"BTC-USD": ONE}, "buy_btc_only")

    def label(self):
        return self.name


class ETHOnlyWeekly:
    name = "eth_only_weekly"

    def decide(self, timestamp, bundle, state):
        return AllocationDecision({"ETH-USD": ONE}, "buy_eth_only")

    def label(self):
        return self.name


class EqualSplitWeekly:
    name = "equal_split_weekly"

    def decide(self, timestamp, bundle, state):
        return AllocationDecision({"BTC-USD": HALF, "ETH-USD": HALF}, "buy_equal_split")

    def label(self):
        return self.name


class BuyStrongerReturnWeekly:
    name = "buy_stronger_return_weekly"

    def __init__(self, window_days):
        self.window_days = window_days

    def decide(self, timestamp, bundle, state):
        btc_return = bundle.trailing_return("BTC-USD", timestamp, self.window_days)
        eth_return = bundle.trailing_return("ETH-USD", timestamp, self.window_days)

        if btc_return is None and eth_return is None:
            return AllocationDecision({"BTC-USD": HALF, "ETH-USD": HALF}, "insufficient_history")
        if eth_return is None or (btc_return is not None and btc_return >= eth_return):
            return AllocationDecision({"BTC-USD": ONE}, "btc_stronger")
        return AllocationDecision({"ETH-USD": ONE}, "eth_stronger")

    def label(self):
        return f"{self.name}(window_days={self.window_days})"


class BuyWeakerReturnWeekly:
    name = "buy_weaker_return_weekly"

    def __init__(self, window_days):
        self.window_days = window_days

    def decide(self, timestamp, bundle, state):
        btc_return = bundle.trailing_return("BTC-USD", timestamp, self.window_days)
        eth_return = bundle.trailing_return("ETH-USD", timestamp, self.window_days)

        if btc_return is None and eth_return is None:
            return AllocationDecision({"BTC-USD": HALF, "ETH-USD": HALF}, "insufficient_history")
        if eth_return is None or (btc_return is not None and btc_return <= eth_return):
            return AllocationDecision({"BTC-USD": ONE}, "btc_weaker")
        return AllocationDecision({"ETH-USD": ONE}, "eth_weaker")

    def label(self):
        return f"{self.name}(window_days={self.window_days})"


class RiskOnETHRiskOffBTC:
    name = "risk_on_eth_risk_off_btc"

    def __init__(self, window_days=50):
        self.window_days = window_days

    def decide(self, timestamp, bundle, state):
        btc_close = bundle.close("BTC-USD", timestamp)
        eth_close = bundle.close("ETH-USD", timestamp)
        btc_ma = bundle.moving_average("BTC-USD", timestamp, self.window_days)
        eth_ma = bundle.moving_average("ETH-USD", timestamp, self.window_days)

        if btc_ma is None or eth_ma is None:
            return AllocationDecision({"BTC-USD": HALF, "ETH-USD": HALF}, "insufficient_history")
        if eth_close > eth_ma:
            return AllocationDecision({"ETH-USD": ONE}, "eth_risk_on")
        if btc_close > btc_ma:
            return AllocationDecision({"BTC-USD": ONE}, "btc_risk_on")
        return AllocationDecision({"BTC-USD": ONE}, "btc_defensive")

    def label(self):
        return f"{self.name}(window_days={self.window_days})"
