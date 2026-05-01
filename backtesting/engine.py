from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass(frozen=True)
class Trade:
    timestamp: datetime
    symbol: str
    side: str
    price: Decimal
    notional_usd: Decimal
    units: Decimal
    fee_usd: Decimal
    reason: str


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    portfolio_value: Decimal
    cash_balance: Decimal
    asset_units: Decimal


@dataclass
class PortfolioState:
    cash_balance: Decimal = ZERO
    asset_units: Decimal = ZERO
    total_contributed: Decimal = ZERO
    total_invested: Decimal = ZERO


@dataclass(frozen=True)
class BacktestResult:
    strategy_name: str
    strategy_label: str
    symbol: str
    contribution_interval: str
    start_timestamp: datetime
    end_timestamp: datetime
    total_contributed: Decimal
    total_invested: Decimal
    ending_cash: Decimal
    asset_units: Decimal
    ending_value: Decimal
    total_return_pct: Decimal
    deployment_rate_pct: Decimal
    max_drawdown_pct: Decimal
    trade_count: int
    trades: list
    equity_curve: list


class BacktestEngine:
    def __init__(self, contribution_amount_usd, interval_days=7, fee_bps=0):
        self.contribution_amount_usd = Decimal(str(contribution_amount_usd))
        self.interval_days = interval_days
        self.fee_bps = Decimal(str(fee_bps))

    def run(self, series, strategy, since):
        state = PortfolioState()
        trades = []
        equity_curve = []

        for index, candle in enumerate(series.candles_since(since)):
            if index % self.interval_days != 0:
                continue

            state.total_contributed += self.contribution_amount_usd
            state.cash_balance += self.contribution_amount_usd

            decision = strategy.decide(candle, series, state)
            buy_notional = min(Decimal(str(decision.buy_usd)), state.cash_balance)
            fee_usd = (buy_notional * self.fee_bps) / Decimal("10000")
            net_notional = buy_notional - fee_usd

            if buy_notional > 0 and net_notional > 0:
                units = net_notional / candle.close
                state.cash_balance -= buy_notional
                state.asset_units += units
                state.total_invested += buy_notional
                trades.append(
                    Trade(
                        timestamp=candle.timestamp,
                        symbol=series.product_id,
                        side="buy",
                        price=candle.close,
                        notional_usd=buy_notional,
                        units=units,
                        fee_usd=fee_usd,
                        reason=decision.reason,
                    )
                )

            equity_curve.append(
                EquityPoint(
                    timestamp=candle.timestamp,
                    portfolio_value=state.cash_balance + (state.asset_units * candle.close),
                    cash_balance=state.cash_balance,
                    asset_units=state.asset_units,
                )
            )

        if not equity_curve:
            raise ValueError("No Sunday candles found in selected range")

        ending_value = equity_curve[-1].portfolio_value
        total_return_pct = ZERO
        if state.total_contributed > 0:
            total_return_pct = ((ending_value / state.total_contributed) - 1) * HUNDRED

        deployment_rate_pct = ZERO
        if state.total_contributed > 0:
            deployment_rate_pct = (state.total_invested / state.total_contributed) * HUNDRED

        return BacktestResult(
            strategy_name=strategy.name,
            strategy_label=strategy.label(),
            symbol=series.product_id,
            contribution_interval=_interval_label(self.interval_days),
            start_timestamp=equity_curve[0].timestamp,
            end_timestamp=equity_curve[-1].timestamp,
            total_contributed=state.total_contributed,
            total_invested=state.total_invested,
            ending_cash=state.cash_balance,
            asset_units=state.asset_units,
            ending_value=ending_value,
            total_return_pct=total_return_pct,
            deployment_rate_pct=deployment_rate_pct,
            max_drawdown_pct=_max_drawdown_pct(equity_curve),
            trade_count=len(trades),
            trades=trades,
            equity_curve=equity_curve,
        )


def _max_drawdown_pct(equity_curve):
    peak = ZERO
    max_drawdown = ZERO

    for point in equity_curve:
        if point.portfolio_value > peak:
            peak = point.portfolio_value
        if peak > 0:
            drawdown = ((peak - point.portfolio_value) / peak) * HUNDRED
            if drawdown > max_drawdown:
                max_drawdown = drawdown

    return max_drawdown


def _interval_label(interval_days):
    return f"{interval_days}d"
