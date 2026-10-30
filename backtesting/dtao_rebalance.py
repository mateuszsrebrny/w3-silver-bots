"""Self-financed top-11 rotation, with optional weekly profit trims."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal


@dataclass(frozen=True)
class RebalanceResult:
    end_tao: Decimal
    cash_tao: Decimal
    max_drawdown: Decimal
    rotations: int
    trims: int
    topups: int
    turnover_tao: Decimal
    skipped_signals: int


def ranked_keys(emissions, signal_day, basket_size):
    ranked = sorted(
        (row for row in emissions.get(signal_day, []) if row[2] > 0),
        key=lambda row: (-row[2], row[0]),
    )[:basket_size]
    return tuple((netuid, registration) for netuid, registration, _ in ranked)


def run_rebalance_backtest(
    cohort, prices, emissions, *, trigger_tao=Decimal("1.2"), topup=False,
    rotation_cadence="monthly", cost_bps=Decimal("0"),
    target_tao=Decimal("1"),
):
    target_tao = Decimal(str(target_tao))
    if target_tao <= 0:
        raise ValueError("Target per subnet must be positive")
    if trigger_tao is not None and trigger_tao <= target_tao:
        raise ValueError("Trim trigger must exceed the target per subnet")
    if trigger_tao is None and topup:
        raise ValueError("Top-ups require the profit-trim variant")
    if rotation_cadence not in ("monthly", "daily"):
        raise ValueError("Rotation cadence must be monthly or daily")
    cost_rate = Decimal(str(cost_bps)) / Decimal("10000")
    if not Decimal("0") <= cost_rate < Decimal("1"):
        raise ValueError("Trade cost must be between 0 and 10000 bps")
    start = cohort.days[0][0]
    first_keys = ranked_keys(emissions, cohort.signal_day, len(cohort.netuids))
    if {netuid for netuid, _ in first_keys} != set(cohort.netuids):
        raise ValueError("Cohort basket does not match its emission signal")
    if any(prices.get((start, netuid), (None,))[0] != registration for netuid, registration in first_keys):
        raise ValueError("Entry registration does not match its emission signal")
    positions = {
        key: target_tao / prices[(start, key[0])][1] for key in first_keys
    }
    lost = set()
    cash = Decimal("0")
    peak = target_tao * len(first_keys)
    max_drawdown = Decimal("0")
    rotations = trims = topups = skipped_signals = 0
    turnover = Decimal("0")

    def spot(day, key):
        observation = prices.get((day, key[0]))
        if observation is None or observation[0] != key[1]:
            lost.add(key)
        return Decimal("0") if key in lost else observation[1]

    for day, _ in cohort.days:
        spots = {key: spot(day, key) for key in positions}
        total = cash + sum(alpha * spots[key] for key, alpha in positions.items())
        peak = max(peak, total)
        max_drawdown = max(max_drawdown, Decimal("1") - total / peak)
        if day == start:
            continue

        rotate_today = rotation_cadence == "daily" or (day.weekday() == 6 and day.day <= 7)
        trim_today = trigger_tao is not None and day.weekday() == 6
        if not rotate_today and not trim_today:
            continue

        desired = None
        if rotate_today:
            signal_day = day - timedelta(days=1)
            if signal_day not in emissions:
                raise ValueError(f"Missing emission signal on {signal_day}")
            candidate = ranked_keys(emissions, signal_day, len(first_keys))
            if len(candidate) != len(first_keys):
                skipped_signals += 1
            elif all(
                prices.get((day, key[0]), (None,))[0] == key[1] for key in candidate
            ):
                desired = set(candidate)
                for key in list(positions):
                    if key not in desired:
                        proceeds = positions.pop(key) * spots[key]
                        cash += proceeds * (Decimal("1") - cost_rate)
                        turnover += proceeds
                        rotations += 1

        if trim_today:
            for key in sorted(positions):
                value = positions[key] * spots[key]
                if value > trigger_tao:
                    proceeds = value - target_tao
                    positions[key] -= proceeds / spots[key]
                    cash += proceeds * (Decimal("1") - cost_rate)
                    turnover += proceeds
                    trims += 1

        if desired is not None:
            entrants = sorted(desired - positions.keys())
            if entrants:
                allocation = cash / len(entrants)
                if trigger_tao is not None:
                    allocation = min(target_tao, allocation)
            else:
                allocation = Decimal("0")
            for key in entrants:
                price = prices[(day, key[0])][1]
                positions[key] = allocation * (Decimal("1") - cost_rate) / price
                spots[key] = price
                cash -= allocation
                turnover += allocation
            if topup and cash > 0:
                gaps = {
                    key: max(Decimal("0"), target_tao - alpha * spots[key])
                    for key, alpha in positions.items() if spots[key] > 0
                }
                total_gap = sum(gaps.values())
                if total_gap > 0:
                    budget = min(cash, total_gap)
                    for key, gap in gaps.items():
                        if gap > 0:
                            spent = budget * gap / total_gap
                            positions[key] += spent * (Decimal("1") - cost_rate) / spots[key]
                            cash -= spent
                            turnover += spent
                            topups += 1

    end = cohort.days[-1][0]
    final = cash + sum(alpha * spot(end, key) for key, alpha in positions.items())
    return RebalanceResult(
        final, cash, max_drawdown, rotations, trims, topups, turnover, skipped_signals
    )
