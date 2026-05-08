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
    allocation_curve: list


@dataclass(frozen=True)
class PortfolioAllocationPoint:
    timestamp: object
    dai_units: Decimal
    btc_units: Decimal
    eth_units: Decimal
    dai_value: Decimal
    btc_value: Decimal
    eth_value: Decimal
    total_value: Decimal
    decision_reason: str
    action: str


@dataclass(frozen=True)
class PortfolioDecisionSnapshot:
    timestamp: object
    decision: object
    current_weights: dict
    target_weights: dict
    current_values: dict
    total_value: Decimal
    trades: list
    allocation_point: PortfolioAllocationPoint


class PortfolioManagementBacktestEngine:
    def __init__(
        self,
        interval_days=7,
        withdrawal_amount_dai="0",
        withdrawal_interval_days=None,
        fee_bps=0,
        max_buy_trade_dai=None,
        max_buy_step_dai=None,
        max_sell_step_dai=None,
    ):
        self.interval_days = interval_days
        self.withdrawal_amount_dai = Decimal(str(withdrawal_amount_dai))
        self.withdrawal_interval_days = withdrawal_interval_days
        self.fee_bps = Decimal(str(fee_bps))
        self.max_buy_trade_dai = (
            Decimal(str(max_buy_trade_dai))
            if max_buy_trade_dai is not None
            else None
        )
        self.max_buy_step_dai = (
            Decimal(str(max_buy_step_dai))
            if max_buy_step_dai is not None
            else None
        )
        self.max_sell_step_dai = (
            Decimal(str(max_sell_step_dai))
            if max_sell_step_dai is not None
            else None
        )

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
        allocation_curve = []

        for index, timestamp in enumerate(bundle.common_timestamps_since(since)):
            if index % self.interval_days != 0:
                continue

            if self.withdrawal_interval_days and index > 0 and index % self.withdrawal_interval_days == 0:
                withdrawn = min(self.withdrawal_amount_dai, state.dai_units)
                state.dai_units -= withdrawn
                state.total_withdrawn += withdrawn

            snapshot = self.evaluate_step(bundle, strategy, timestamp, state)
            trades.extend(snapshot.trades)
            equity_curve.append(
                EquityPoint(
                    timestamp=timestamp,
                    portfolio_value=snapshot.allocation_point.total_value,
                    cash_balance=state.dai_units,
                    asset_units=ZERO,
                )
            )
            allocation_curve.append(snapshot.allocation_point)

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
            allocation_curve=allocation_curve,
        )

    def evaluate_step(self, bundle, strategy, timestamp, state):
        decision = strategy.decide(timestamp, bundle, state)
        current_values = _position_values(bundle, state.positions, timestamp)
        total_value = state.dai_units + sum(current_values.values(), ZERO)

        current_weights = {
            "BTC-USD": current_values["BTC-USD"] / total_value if total_value > 0 else ZERO,
            "ETH-USD": current_values["ETH-USD"] / total_value if total_value > 0 else ZERO,
            "DAI": state.dai_units / total_value if total_value > 0 else ZERO,
        }

        target_weights = {
            symbol: Decimal(str(weight))
            for symbol, weight in decision.target_weights.items()
        }
        rebalance_fraction = Decimal(str(decision.rebalance_fraction))
        if hasattr(decision, "buy_budget_fraction"):
            return self._evaluate_budgeted_step(
                bundle,
                timestamp,
                state,
                decision,
                current_values,
                total_value,
                current_weights,
                target_weights,
                rebalance_fraction,
            )

        step_trades = []
        for symbol in ["BTC-USD", "ETH-USD"]:
            current_weight = current_weights[symbol]
            target_weight = target_weights[symbol]
            diff_weight = (target_weight - current_weight) * rebalance_fraction
            if diff_weight == 0:
                continue

            target_notional = total_value * abs(diff_weight)
            price = bundle.close(symbol, timestamp)
            fee_dai = (target_notional * self.fee_bps) / Decimal("10000")

            if diff_weight > 0:
                affordable = min(target_notional, state.dai_units)
                if self.max_buy_trade_dai is not None:
                    affordable = min(affordable, self.max_buy_trade_dai)
                if affordable <= 0:
                    continue
                fee_paid = min(fee_dai, affordable)
                net_dai = affordable - fee_paid
                units = net_dai / price
                state.dai_units -= affordable
                state.positions[symbol] += units
                state.total_bought_dai += affordable
                step_trades.append(
                    Trade(
                        timestamp=timestamp,
                        symbol=symbol,
                        side="buy",
                        price=price,
                        notional_usd=affordable,
                        units=units,
                        fee_usd=fee_paid,
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
                step_trades.append(
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

        return _build_snapshot(
            bundle=bundle,
            timestamp=timestamp,
            state=state,
            decision=decision,
            current_weights=current_weights,
            target_weights=target_weights,
            current_values=current_values,
            total_value=total_value,
            step_trades=step_trades,
        )

    def _evaluate_budgeted_step(
        self,
        bundle,
        timestamp,
        state,
        decision,
        current_values,
        total_value,
        current_weights,
        target_weights,
        rebalance_fraction,
    ):
        step_trades = []
        buy_candidates = []
        sell_candidates = []

        for symbol in ["BTC-USD", "ETH-USD"]:
            current_weight = current_weights[symbol]
            target_weight = target_weights[symbol]
            diff_weight = (target_weight - current_weight) * rebalance_fraction
            if diff_weight == 0:
                continue

            target_notional = total_value * abs(diff_weight)
            price = bundle.close(symbol, timestamp)
            if diff_weight > 0:
                buy_candidates.append((symbol, target_notional, price))
            else:
                max_sell_value = current_values[symbol]
                sell_candidates.append((symbol, min(target_notional, max_sell_value), price))

        if buy_candidates:
            desired_total = sum((item[1] for item in buy_candidates), ZERO)
            if self.max_buy_step_dai is not None:
                budget_total = min(state.dai_units, self.max_buy_step_dai * Decimal(str(decision.buy_budget_fraction)))
            else:
                budget_total = min(state.dai_units, desired_total * Decimal(str(decision.buy_budget_fraction)))
            allocations = _allocate_budget(
                buy_candidates,
                budget_total,
                {
                    symbol: Decimal(str(decision.buy_weights.get(symbol, ZERO)))
                    for symbol, _, _ in buy_candidates
                },
            )
            for symbol, affordable, price in allocations:
                if self.max_buy_trade_dai is not None:
                    affordable = min(affordable, self.max_buy_trade_dai)
                if affordable <= 0:
                    continue
                fee_dai = (affordable * self.fee_bps) / Decimal("10000")
                fee_paid = min(fee_dai, affordable)
                net_dai = affordable - fee_paid
                units = net_dai / price
                state.dai_units -= affordable
                state.positions[symbol] += units
                state.total_bought_dai += affordable
                step_trades.append(
                    Trade(
                        timestamp=timestamp,
                        symbol=symbol,
                        side="buy",
                        price=price,
                        notional_usd=affordable,
                        units=units,
                        fee_usd=fee_paid,
                        reason=decision.reason,
                    )
                )

        if sell_candidates:
            desired_total = sum((item[1] for item in sell_candidates), ZERO)
            if self.max_sell_step_dai is not None:
                budget_total = min(desired_total, self.max_sell_step_dai * Decimal(str(decision.sell_budget_fraction)))
            else:
                budget_total = desired_total * Decimal(str(decision.sell_budget_fraction))
            allocations = _allocate_budget(
                sell_candidates,
                budget_total,
                {
                    symbol: Decimal(str(decision.sell_weights.get(symbol, ZERO)))
                    for symbol, _, _ in sell_candidates
                },
            )
            for symbol, sell_value, price in allocations:
                if sell_value <= 0:
                    continue
                units = sell_value / price
                fee_dai = (sell_value * self.fee_bps) / Decimal("10000")
                fee_paid = min(fee_dai, sell_value)
                state.positions[symbol] -= units
                state.dai_units += sell_value - fee_paid
                state.total_sold_dai += sell_value
                step_trades.append(
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

        return _build_snapshot(
            bundle=bundle,
            timestamp=timestamp,
            state=state,
            decision=decision,
            current_weights=current_weights,
            target_weights=target_weights,
            current_values=current_values,
            total_value=total_value,
            step_trades=step_trades,
        )


def _position_values(bundle, positions, timestamp):
    return {
        symbol: units * bundle.close(symbol, timestamp)
        for symbol, units in positions.items()
    }


def _summarize_step_actions(step_trades):
    if not step_trades:
        return "hold"

    action_parts = []
    for symbol in ["BTC-USD", "ETH-USD"]:
        symbol_trades = [trade for trade in step_trades if trade.symbol == symbol]
        if not symbol_trades:
            continue
        sides = {trade.side for trade in symbol_trades}
        asset = "btc" if symbol == "BTC-USD" else "eth"
        if sides == {"buy"}:
            action_parts.append(f"buy_{asset}")
        elif sides == {"sell"}:
            action_parts.append(f"sell_{asset}")
        else:
            action_parts.append(f"rebalance_{asset}")

    return "+".join(action_parts) if action_parts else "hold"


def _allocate_budget(candidates, total_budget, preferred_weights):
    allocations = {symbol: ZERO for symbol, _, _ in candidates}
    remaining = {
        symbol: desired
        for symbol, desired, _ in candidates
    }
    prices = {symbol: price for symbol, _, price in candidates}
    budget_left = min(total_budget, sum(remaining.values(), ZERO))

    while budget_left > ZERO:
        active = [symbol for symbol, desired, _ in candidates if remaining[symbol] > ZERO]
        if not active:
            break
        weight_sum = sum((preferred_weights.get(symbol, ZERO) for symbol in active), ZERO)
        if weight_sum <= ZERO:
            even_weight = ONE / Decimal(str(len(active)))
            weights = {symbol: even_weight for symbol in active}
        else:
            weights = {symbol: preferred_weights.get(symbol, ZERO) / weight_sum for symbol in active}

        spent_this_round = ZERO
        for symbol in active:
            slice_budget = min(remaining[symbol], budget_left * weights[symbol])
            if slice_budget <= ZERO:
                continue
            allocations[symbol] += slice_budget
            remaining[symbol] -= slice_budget
            spent_this_round += slice_budget
        if spent_this_round <= ZERO:
            break
        budget_left -= spent_this_round

    return [(symbol, allocations[symbol], prices[symbol]) for symbol, _, _ in candidates]


def _build_snapshot(bundle, timestamp, state, decision, current_weights, target_weights, current_values, total_value, step_trades):
    ending_values = _position_values(bundle, state.positions, timestamp)
    portfolio_value = state.dai_units + sum(ending_values.values(), ZERO)
    allocation_point = PortfolioAllocationPoint(
        timestamp=timestamp,
        dai_units=state.dai_units,
        btc_units=state.positions["BTC-USD"],
        eth_units=state.positions["ETH-USD"],
        dai_value=state.dai_units,
        btc_value=ending_values["BTC-USD"],
        eth_value=ending_values["ETH-USD"],
        total_value=portfolio_value,
        decision_reason=decision.reason,
        action=_summarize_step_actions(step_trades),
    )
    return PortfolioDecisionSnapshot(
        timestamp=timestamp,
        decision=decision,
        current_weights=current_weights,
        target_weights=target_weights,
        current_values=current_values,
        total_value=total_value,
        trades=step_trades,
        allocation_point=allocation_point,
    )
