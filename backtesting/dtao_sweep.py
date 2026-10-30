"""Compare price-only trim thresholds across monthly entry dates."""

from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from backtesting.dtao import Result, run_price_only_backtest


@dataclass(frozen=True)
class ThresholdSummary:
    trigger_tao: Decimal
    windows: int
    trim_wins: int
    median_delta_tao: Decimal
    lower_drawdown_windows: int


def monthly_windows(days, minimum_days=90):
    if minimum_days < 2:
        raise ValueError("minimum_days must be at least 2")
    starts = []
    last_month = None
    for index, (day, _) in enumerate(days):
        month = (day.year, day.month)
        if month != last_month:
            if len(days) - index >= minimum_days:
                starts.append(index)
            last_month = month
    return [days[index:] for index in starts]


def run_threshold_sweep(days, triggers, minimum_days=90, target_tao=Decimal("1")):
    if len(set(triggers)) != len(triggers):
        raise ValueError("Trim triggers must be distinct")
    windows = monthly_windows(days, minimum_days)
    if not windows:
        raise ValueError("No monthly windows meet minimum_days")

    results: dict[Decimal, list[Result]] = {}
    summaries = []
    for trigger in triggers:
        runs = [run_price_only_backtest(window, target_tao, trigger) for window in windows]
        results[trigger] = runs
        deltas = [run.trim_tao - run.hold_tao for run in runs]
        summaries.append(
            ThresholdSummary(
                trigger_tao=trigger,
                windows=len(runs),
                trim_wins=sum(delta > 0 for delta in deltas),
                median_delta_tao=median(deltas),
                lower_drawdown_windows=sum(
                    run.trim_max_drawdown < run.hold_max_drawdown for run in runs
                ),
            )
        )
    return results, summaries
