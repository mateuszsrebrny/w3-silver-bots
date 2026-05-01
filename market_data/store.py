import csv
from pathlib import Path

from market_data.candles import Candle, format_csv_timestamp, granularity_to_timedelta, parse_csv_timestamp


class CandleStore:
    FIELDNAMES = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "source",
        "product_id",
        "granularity",
    ]

    def __init__(self, path):
        self.path = Path(path)

    def exists(self):
        return self.path.exists()

    def load(self, validate=True):
        if not self.exists():
            return []

        candles = []
        with self.path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                candles.append(
                    Candle(
                        timestamp=parse_csv_timestamp(row["timestamp"]),
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                        source=row["source"],
                        product_id=row["product_id"],
                        granularity=row["granularity"],
                    )
                )

        normalized = [
            Candle(
                timestamp=candle.timestamp,
                open=self._to_decimal(candle.open),
                high=self._to_decimal(candle.high),
                low=self._to_decimal(candle.low),
                close=self._to_decimal(candle.close),
                volume=self._to_decimal(candle.volume),
                source=candle.source,
                product_id=candle.product_id,
                granularity=candle.granularity,
            )
            for candle in candles
        ]
        if validate:
            self.validate(normalized)
        return normalized

    def save(self, candles):
        self.validate(candles)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            for candle in candles:
                writer.writerow(
                    {
                        "timestamp": format_csv_timestamp(candle.timestamp),
                        "open": str(candle.open),
                        "high": str(candle.high),
                        "low": str(candle.low),
                        "close": str(candle.close),
                        "volume": str(candle.volume),
                        "source": candle.source,
                        "product_id": candle.product_id,
                        "granularity": candle.granularity,
                    }
                )

    def merge(self, existing_candles, new_candles):
        merged = {candle.timestamp: candle for candle in existing_candles}
        merged.update({candle.timestamp: candle for candle in new_candles})
        sorted_candles = [merged[timestamp] for timestamp in sorted(merged)]
        self.validate(sorted_candles)
        return sorted_candles

    def find_missing_timestamps(self, candles):
        if len(candles) < 2:
            return []

        step = granularity_to_timedelta(candles[0].granularity)
        missing = []
        previous = candles[0].timestamp
        for candle in candles[1:]:
            expected = previous + step
            while expected < candle.timestamp:
                missing.append(expected)
                expected += step
            previous = candle.timestamp
        return missing

    def validate(self, candles):
        if not candles:
            return

        first = candles[0]
        step = granularity_to_timedelta(first.granularity)
        seen = set()
        previous = None

        for candle in candles:
            if candle.timestamp in seen:
                raise ValueError(f"Duplicate candle timestamp: {candle.timestamp}")
            seen.add(candle.timestamp)

            if candle.product_id != first.product_id:
                raise ValueError("Mixed product_id in candle series")
            if candle.granularity != first.granularity:
                raise ValueError("Mixed granularity in candle series")
            if candle.source != first.source:
                raise ValueError("Mixed source in candle series")

            if candle.low > candle.high:
                raise ValueError("Candle low is above high")
            if not (candle.low <= candle.open <= candle.high):
                raise ValueError("Candle open is outside low/high range")
            if not (candle.low <= candle.close <= candle.high):
                raise ValueError("Candle close is outside low/high range")

            if previous is not None and candle.timestamp <= previous.timestamp:
                raise ValueError("Candles are not strictly increasing")
            previous = candle

        missing = self.find_missing_timestamps(candles)
        if missing:
            raise ValueError(f"Missing candle timestamps: {missing[0]}")

        # Touch the step so unsupported granularities fail early.
        _ = step

    @staticmethod
    def _to_decimal(value):
        from decimal import Decimal

        return Decimal(str(value))
