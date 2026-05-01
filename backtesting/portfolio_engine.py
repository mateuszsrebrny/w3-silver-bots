from dataclasses import dataclass
from decimal import Decimal

from backtesting.engine import EquityPoint, HUNDRED, Trade, ZERO, _max_drawdown_pct


@dataclass
class PortfolioManagementState:
    dai_units: Decimal
    positions: dict
    total_withdrawn: Decimal = ZERO
    total_bought_dai: Decimal = ZERO
    total_sold_dai: Decimal = ZERO


@dataclass(frozen=True)
class PortfolioBacktestResult:
    strategy_name: str
    strategy_label: str
    symbol: str
    contribution_interval: str
    start_timestamp: object
    end_timestamp: object
    initial_value: Decimal
    gross_buys_dai: Decimal
    gross_sells_dai: Decimal
    net_buys_dai: Decimal
    ending_dai: Decimal
    ending_btc_units: Decimal
    ending_eth_units: Decimal
    ending_value: Decimal
    total_withdrawn_dai: Decimal
    realized_value: Decimal
    total_return_pct: Decimal
    turnover_pct: Decimal
    max_drawdown_pct: Decimal
    trade_count: int
    trades: list
    equity_curve: list


class PortfolioManagementBacktestEngine:
    def __init__(
        self,
        interval_days=7,
        withdrawal_amount_dai="0",
        withdrawal_interval_days=None,
        fee_bps=0,
    ):
        self.interval_days = interval_days
        self.withdrawal_amount_dai = Decimal(str(withdrawal_amount_dai))
        self.withdrawal_interval_days = withdrawal_interval_days
        self.fee_bps = Decimal(str(fee_bps))

    def run(self, bundle, strategy, since, initial_btc, initial_eth, initial_dai):
        state = PortfolioManagementState(
            dai_units=Decimal(str(initial_dai)),
            positions={
                "BTC-USD": Decimal(str(initial_btc)),
                "ETH-USD": Decimal(str(initial_eth)),
            },
        )
        trades = []
        equity_curve = []

        for index, timestamp in enumerate(bundle.common_timestamps_since(since)):
            if index % self.interval_days != 0:
                continue

            if self.withdrawal_interval_days and index > 0 and index % self.withdrawal_interval_days == 0:
                withdrawn = min(self.withdrawal_amount_dai, state.dai_units)
                state.dai_units -= withdrawn
                state.total_withdrawn += withdrawn

            decision = strategy.decide(timestamp, bundle, state)
            current_values = _position_values(bundle, state.positions, timestamp)
            total_value = state.dai_units + sum(current_values.values(), ZERO)

            current_weights = {
                "BTC-USD": current_values["BTC-USD"] / total_value if total_value > 0 else ZERO,
                "ETH-USD": current_values["ETH-USD"] / total_value if total_value > 0 else ZERO,
                "DAI": state.dai_units / total_value if total_value > 0 else ZERO,
            }

            target_weights = decision.target_weights
            rebalance_fraction = Decimal(str(decision.rebalance_fraction))

            for symbol in ["BTC-USD", "ETH-USD"]:
                current_weight = current_weights[symbol]
                target_weight = Decimal(str(target_weights[symbol]))
                diff_weight = (target_weight - current_weight) * rebalance_fraction
                if diff_weight == 0:
                    continue

                target_notional = total_value * abs(diff_weight)
                price = bundle.close(symbol, timestamp)
                fee_dai = (target_notional * self.fee_bps) / Decimal("10000")

                if diff_weight > 0:
                    affordable = min(target_notional, state.dai_units)
                    if affordable <= 0:
                        continue
                    net_dai = affordable - min(fee_dai, affordable)
                    units = net_dai / price
                    state.dai_units -= affordable
                    state.positions[symbol] += units
                    state.total_bought_dai += affordable
                    trades.append(
                        Trade(
                            timestamp=timestamp,
                            symbol=symbol,
                            side="buy",
                            price=price,
                            notional_usd=affordable,
                            units=units,
                            fee_usd=min(fee_dai, affordable),
                            reason=decision.reason,
                        )
                    )
                else:
                    max_sell_value = current_values[symbol]
                    sell_value = min(target_notional, max_sell_value)
                    if sell_value <= 0:
                        continue
                    units = sell_value / price
                    fee_paid = min(fee_dai, sell_value)
                    state.positions[symbol] -= units
                    state.dai_units += sell_value - fee_paid
                    state.total_sold_dai += sell_value
                    trades.append(
                        Trade(
                            timestamp=timestamp,
                            symbol=symbol,
                            side="sell",
                            price=price,
                            notional_usd=sell_value,
                            units=units,
                            fee_usd=fee_paid,
                            reason=decision.reason,
                        )
                    )

            portfolio_value = state.dai_units + sum(
                _position_values(bundle, state.positions, timestamp).values(),
                ZERO,
            )
            equity_curve.append(
                EquityPoint(
                    timestamp=timestamp,
                    portfolio_value=portfolio_value,
                    cash_balance=state.dai_units,
                    asset_units=ZERO,
                )
            )

        if not equity_curve:
            raise ValueError("No portfolio evaluation points found in selected range")

        ending_value = equity_curve[-1].portfolio_value
        initial_value = (
            Decimal(str(initial_dai))
            + (Decimal(str(initial_btc)) * bundle.close("BTC-USD", equity_curve[0].timestamp))
            + (Decimal(str(initial_eth)) * bundle.close("ETH-USD", equity_curve[0].timestamp))
        )
        realized_value = ending_value + state.total_withdrawn
        total_return_pct = ZERO
        if initial_value > 0:
            total_return_pct = ((realized_value / initial_value) - 1) * HUNDRED

        gross_buys_dai = state.total_bought_dai
        gross_sells_dai = state.total_sold_dai
        net_buys_dai = gross_buys_dai - gross_sells_dai
        turnover_pct = ZERO
        if initial_value > 0:
            turnover_pct = ((gross_buys_dai + gross_sells_dai) / initial_value) * HUNDRED

        return PortfolioBacktestResult(
            strategy_name=strategy.name,
            strategy_label=strategy.label(),
            symbol="BTC-USD+ETH-USD+DAI",
            contribution_interval=f"{self.interval_days}d",
            start_timestamp=equity_curve[0].timestamp,
            end_timestamp=equity_curve[-1].timestamp,
            initial_value=initial_value,
            gross_buys_dai=gross_buys_dai,
            gross_sells_dai=gross_sells_dai,
            net_buys_dai=net_buys_dai,
            ending_dai=state.dai_units,
            ending_btc_units=state.positions["BTC-USD"],
            ending_eth_units=state.positions["ETH-USD"],
            ending_value=ending_value,
            total_withdrawn_dai=state.total_withdrawn,
            realized_value=realized_value,
            total_return_pct=total_return_pct,
            turnover_pct=turnover_pct,
            max_drawdown_pct=_max_drawdown_pct(equity_curve),
            trade_count=len(trades),
            trades=trades,
            equity_curve=equity_curve,
        )


def _position_values(bundle, positions, timestamp):
    return {
        symbol: units * bundle.close(symbol, timestamp)
        for symbol, units in positions.items()
    }
