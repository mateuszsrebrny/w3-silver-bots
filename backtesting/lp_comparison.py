from dataclasses import dataclass
from decimal import Decimal

from backtesting.engine import EquityPoint, HUNDRED, ZERO, _max_drawdown_pct


ANNUALIZATION_DAYS = Decimal("365.2425")


@dataclass(frozen=True)
class LPComparisonResult:
    strategy_name: str
    strategy_label: str
    symbol: str
    pair_name: str
    contribution_interval: str
    start_timestamp: object
    end_timestamp: object
    initial_value: Decimal
    ending_value: Decimal
    total_return_pct: Decimal
    max_drawdown_pct: Decimal
    fee_yield_pct: Decimal
    yield_mode: str
    equity_curve: list


class LPComparisonBacktestEngine:
    def __init__(self, fee_yield_pct="0", yield_mode="apr"):
        self.fee_yield_pct = Decimal(str(fee_yield_pct))
        self.yield_mode = yield_mode

    def run_pair(self, bundle, pair_name, since, initial_value):
        timestamps = bundle.common_timestamps_since(since)
        if not timestamps:
            raise ValueError("No common timestamps found in selected range")

        symbol_a, symbol_b = bundle.symbols()
        initial_value = Decimal(str(initial_value))
        price_a0 = bundle.close(symbol_a, timestamps[0])
        price_b0 = bundle.close(symbol_b, timestamps[0])

        hold_a_units = initial_value / price_a0
        hold_b_units = initial_value / price_b0
        hold_50_a_units = (initial_value / Decimal("2")) / price_a0
        hold_50_b_units = (initial_value / Decimal("2")) / price_b0

        hold_a_curve = []
        hold_b_curve = []
        hold_50_curve = []
        lp_curve = []

        for timestamp in timestamps:
            price_a = bundle.close(symbol_a, timestamp)
            price_b = bundle.close(symbol_b, timestamp)
            elapsed_days = Decimal(str((timestamp - timestamps[0]).days))

            hold_a_value = hold_a_units * price_a
            hold_b_value = hold_b_units * price_b
            hold_50_value = (hold_50_a_units * price_a) + (hold_50_b_units * price_b)
            relative_ratio = (price_a / price_b) / (price_a0 / price_b0)
            lp_raw_value = hold_50_value * _impermanent_loss_factor(relative_ratio)
            lp_value = lp_raw_value * _yield_multiplier(
                self.fee_yield_pct,
                elapsed_days,
                self.yield_mode,
            )

            hold_a_curve.append(
                EquityPoint(timestamp, hold_a_value, ZERO, hold_a_units)
            )
            hold_b_curve.append(
                EquityPoint(timestamp, hold_b_value, ZERO, hold_b_units)
            )
            hold_50_curve.append(
                EquityPoint(timestamp, hold_50_value, ZERO, ZERO)
            )
            lp_curve.append(
                EquityPoint(timestamp, lp_value, ZERO, ZERO)
            )

        return [
            _build_result(
                strategy_name=f"{pair_name}_hold_{symbol_a.lower().replace('-', '_')}",
                strategy_label=f"Hold {symbol_a}",
                pair_name=pair_name,
                symbol=bundle.symbol_label(),
                initial_value=initial_value,
                fee_yield_pct=ZERO,
                yield_mode=self.yield_mode,
                equity_curve=hold_a_curve,
            ),
            _build_result(
                strategy_name=f"{pair_name}_hold_{symbol_b.lower().replace('-', '_')}",
                strategy_label=f"Hold {symbol_b}",
                pair_name=pair_name,
                symbol=bundle.symbol_label(),
                initial_value=initial_value,
                fee_yield_pct=ZERO,
                yield_mode=self.yield_mode,
                equity_curve=hold_b_curve,
            ),
            _build_result(
                strategy_name=f"{pair_name}_hold_50_50",
                strategy_label=f"Hold 50/50 {pair_name}",
                pair_name=pair_name,
                symbol=bundle.symbol_label(),
                initial_value=initial_value,
                fee_yield_pct=ZERO,
                yield_mode=self.yield_mode,
                equity_curve=hold_50_curve,
            ),
            _build_result(
                strategy_name=f"{pair_name}_lp_50_50",
                strategy_label=f"LP 50/50 {pair_name} + {self.fee_yield_pct}% {self.yield_mode.upper()}",
                pair_name=pair_name,
                symbol=bundle.symbol_label(),
                initial_value=initial_value,
                fee_yield_pct=self.fee_yield_pct,
                yield_mode=self.yield_mode,
                equity_curve=lp_curve,
            ),
        ]


def _build_result(
    strategy_name,
    strategy_label,
    pair_name,
    symbol,
    initial_value,
    fee_yield_pct,
    yield_mode,
    equity_curve,
):
    ending_value = equity_curve[-1].portfolio_value
    total_return_pct = ((ending_value / initial_value) - 1) * HUNDRED if initial_value > 0 else ZERO
    return LPComparisonResult(
        strategy_name=strategy_name,
        strategy_label=strategy_label,
        symbol=symbol,
        pair_name=pair_name,
        contribution_interval="1d",
        start_timestamp=equity_curve[0].timestamp,
        end_timestamp=equity_curve[-1].timestamp,
        initial_value=initial_value,
        ending_value=ending_value,
        total_return_pct=total_return_pct,
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        fee_yield_pct=fee_yield_pct,
        yield_mode=yield_mode,
        equity_curve=equity_curve,
    )


def _impermanent_loss_factor(relative_ratio):
    ratio = Decimal(str(relative_ratio))
    if ratio <= 0:
        raise ValueError("Relative ratio must be positive")
    return (Decimal("2") * ratio.sqrt()) / (Decimal("1") + ratio)


def _yield_multiplier(fee_yield_pct, elapsed_days, yield_mode):
    fee_rate = Decimal(str(fee_yield_pct)) / HUNDRED
    elapsed_days = Decimal(str(elapsed_days))
    if yield_mode == "apr":
        return Decimal("1") + (fee_rate * elapsed_days / ANNUALIZATION_DAYS)
    if yield_mode == "apy":
        years = float(elapsed_days / ANNUALIZATION_DAYS)
        return Decimal(str((1 + float(fee_rate)) ** years))
    raise ValueError(f"Unsupported yield mode: {yield_mode}")
