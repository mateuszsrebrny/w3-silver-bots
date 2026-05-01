from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal


UTC = timezone.utc
DAILY_GRANULARITY_SECONDS = 24 * 60 * 60


@dataclass(frozen=True, order=True)
class Candle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str
    product_id: str
    granularity: str


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def granularity_to_seconds(granularity: str) -> int:
    if granularity == "1d":
        return DAILY_GRANULARITY_SECONDS
    raise ValueError(f"Unsupported granularity: {granularity}")


def granularity_to_timedelta(granularity: str) -> timedelta:
    return timedelta(seconds=granularity_to_seconds(granularity))


def format_coinbase_timestamp(value: datetime) -> str:
    return ensure_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_csv_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def format_csv_timestamp(value: datetime) -> str:
    return ensure_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")

