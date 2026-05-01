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


class BuyFurtherBelowMAWeekly:
    name = "buy_further_below_ma_weekly"

    def __init__(self, window_days=50):
        self.window_days = window_days

    def decide(self, timestamp, bundle, state):
        btc_gap = _ma_gap(bundle, "BTC-USD", timestamp, self.window_days)
        eth_gap = _ma_gap(bundle, "ETH-USD", timestamp, self.window_days)
        if btc_gap is None or eth_gap is None:
            return AllocationDecision({"BTC-USD": HALF, "ETH-USD": HALF}, "insufficient_history")
        if btc_gap < 0 and eth_gap < 0:
            if btc_gap <= eth_gap:
                return AllocationDecision({"BTC-USD": ONE}, "btc_further_below_ma")
            return AllocationDecision({"ETH-USD": ONE}, "eth_further_below_ma")
        if btc_gap < 0:
            return AllocationDecision({"BTC-USD": ONE}, "btc_below_ma")
        if eth_gap < 0:
            return AllocationDecision({"ETH-USD": ONE}, "eth_below_ma")
        return AllocationDecision({"BTC-USD": ONE}, "no_asset_below_ma_btc_default")

    def label(self):
        return f"{self.name}(window_days={self.window_days})"


class BuyETHBelowMAOtherwiseBTC:
    name = "buy_eth_below_ma_otherwise_btc"

    def __init__(self, window_days=50):
        self.window_days = window_days

    def decide(self, timestamp, bundle, state):
        eth_gap = _ma_gap(bundle, "ETH-USD", timestamp, self.window_days)
        if eth_gap is None:
            return AllocationDecision({"BTC-USD": HALF, "ETH-USD": HALF}, "insufficient_history")
        if eth_gap < 0:
            return AllocationDecision({"ETH-USD": ONE}, "eth_below_ma")
        return AllocationDecision({"BTC-USD": ONE}, "eth_not_below_ma_btc_default")

    def label(self):
        return f"{self.name}(window_days={self.window_days})"


class BuyBTCBelowMAOtherwiseETH:
    name = "buy_btc_below_ma_otherwise_eth"

    def __init__(self, window_days=50):
        self.window_days = window_days

    def decide(self, timestamp, bundle, state):
        btc_gap = _ma_gap(bundle, "BTC-USD", timestamp, self.window_days)
        if btc_gap is None:
            return AllocationDecision({"BTC-USD": HALF, "ETH-USD": HALF}, "insufficient_history")
        if btc_gap < 0:
            return AllocationDecision({"BTC-USD": ONE}, "btc_below_ma")
        return AllocationDecision({"ETH-USD": ONE}, "btc_not_below_ma_eth_default")

    def label(self):
        return f"{self.name}(window_days={self.window_days})"


class BTCCoreETHOverlay:
    name = "btc_core_eth_overlay"

    def __init__(self, ma_window_days=50, return_window_days=84, eth_weight="0.30"):
        self.ma_window_days = ma_window_days
        self.return_window_days = return_window_days
        self.eth_weight = Decimal(str(eth_weight))
        self.btc_weight = ONE - self.eth_weight

    def decide(self, timestamp, bundle, state):
        eth_gap = _ma_gap(bundle, "ETH-USD", timestamp, self.ma_window_days)
        eth_return = bundle.trailing_return("ETH-USD", timestamp, self.return_window_days)
        btc_return = bundle.trailing_return("BTC-USD", timestamp, self.return_window_days)
        if eth_gap is None or eth_return is None or btc_return is None:
            return AllocationDecision({"BTC-USD": ONE}, "insufficient_history_btc_core")
        if eth_gap > 0 and eth_return > btc_return:
            return AllocationDecision(
                {"BTC-USD": self.btc_weight, "ETH-USD": self.eth_weight},
                "eth_overlay_enabled",
            )
        return AllocationDecision({"BTC-USD": ONE}, "btc_core_only")

    def label(self):
        return (
            f"{self.name}(ma_window_days={self.ma_window_days},"
            f"return_window_days={self.return_window_days},eth_weight={self.eth_weight})"
        )


def _ma_gap(bundle, symbol, timestamp, window_days):
    close = bundle.close(symbol, timestamp)
    moving_average = bundle.moving_average(symbol, timestamp, window_days)
    if close is None or moving_average is None or moving_average == 0:
        return None
    return (close / moving_average) - ONE
