from dataclasses import dataclass, field
from decimal import Decimal

from backtesting.engine import BacktestResult, EquityPoint, HUNDRED, Trade, ZERO, _max_drawdown_pct


@dataclass
class MultiAssetPortfolioState:
    cash_balance: Decimal = ZERO
    positions: dict = field(default_factory=dict)
    total_contributed: Decimal = ZERO
    total_invested: Decimal = ZERO


class RotationBacktestEngine:
    def __init__(self, contribution_amount_usd, interval_days=7, fee_bps=0):
        self.contribution_amount_usd = Decimal(str(contribution_amount_usd))
        self.interval_days = interval_days
        self.fee_bps = Decimal(str(fee_bps))

    def run(self, bundle, strategy, since):
        state = MultiAssetPortfolioState(
            positions={symbol: ZERO for symbol in bundle.symbols()}
        )
        trades = []
        equity_curve = []

        for index, timestamp in enumerate(bundle.common_timestamps_since(since)):
            if index % self.interval_days != 0:
                continue

            state.total_contributed += self.contribution_amount_usd
            state.cash_balance += self.contribution_amount_usd

            decision = strategy.decide(timestamp, bundle, state)
            weights = _normalize_weights(decision.weights, bundle.symbols())
            deployed_this_week = ZERO

            for symbol, weight in weights.items():
                if weight <= 0:
                    continue
                buy_notional = state.cash_balance * weight if deployed_this_week == ZERO else self.contribution_amount_usd * weight
                # Always allocate the full weekly contribution across weights, not the whole accumulated cash.
                buy_notional = self.contribution_amount_usd * weight
                if buy_notional <= 0:
                    continue
                fee_usd = (buy_notional * self.fee_bps) / Decimal("10000")
                net_notional = buy_notional - fee_usd
                price = bundle.close(symbol, timestamp)
                units = net_notional / price
                state.cash_balance -= buy_notional
                state.positions[symbol] += units
                state.total_invested += buy_notional
                deployed_this_week += buy_notional
                trades.append(
                    Trade(
                        timestamp=timestamp,
                        symbol=symbol,
                        side="buy",
                        price=price,
                        notional_usd=buy_notional,
                        units=units,
                        fee_usd=fee_usd,
                        reason=decision.reason,
                    )
                )

            portfolio_value = state.cash_balance
            for symbol, units in state.positions.items():
                portfolio_value += units * bundle.close(symbol, timestamp)

            equity_curve.append(
                EquityPoint(
                    timestamp=timestamp,
                    portfolio_value=portfolio_value,
                    cash_balance=state.cash_balance,
                    asset_units=ZERO,
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
            symbol=bundle.symbol_label(),
            contribution_interval=_interval_label(self.interval_days),
            start_timestamp=equity_curve[0].timestamp,
            end_timestamp=equity_curve[-1].timestamp,
            total_contributed=state.total_contributed,
            total_invested=state.total_invested,
            ending_cash=state.cash_balance,
            asset_units=ZERO,
            ending_value=ending_value,
            total_return_pct=total_return_pct,
            deployment_rate_pct=deployment_rate_pct,
            max_drawdown_pct=_max_drawdown_pct(equity_curve),
            trade_count=len(trades),
            trades=trades,
            equity_curve=equity_curve,
        )


def _normalize_weights(weights, allowed_symbols):
    normalized = {symbol: Decimal(str(weights.get(symbol, ZERO))) for symbol in allowed_symbols}
    total = sum(normalized.values(), ZERO)
    if total != Decimal("1"):
        raise ValueError(f"Strategy weights must sum to 1, got {total}")
    return normalized


def _interval_label(interval_days):
    return f"{interval_days}d"
