from datetime import datetime

from market_data.candles import ensure_utc, granularity_to_timedelta


class MarketDataSyncService:
    def __init__(self, provider, store):
        self.provider = provider
        self.store = store

    def seed_history(self, product_id, granularity, start, end):
        candles = self.provider.fetch_candles(product_id, granularity, start, end)
        self.store.save(candles)
        return candles

    def update_history(self, product_id, granularity, end):
        existing = self.store.load()
        if not existing:
            raise ValueError("Cannot update empty store; seed history first")

        next_timestamp = existing[-1].timestamp + granularity_to_timedelta(granularity)
        if next_timestamp >= ensure_utc(end):
            return existing

        new_candles = self.provider.fetch_candles(
            product_id,
            granularity,
            next_timestamp,
            end,
        )
        merged = self.store.merge(existing, new_candles)
        self.store.save(merged)
        return merged

    def repair_gaps(self, product_id, granularity, end):
        candles = self.store.load(validate=False)
        if not candles:
            return []

        missing = self.store.find_missing_timestamps(candles)
        if not missing:
            return candles

        step = granularity_to_timedelta(granularity)
        repaired = candles
        for timestamp in missing:
            new_candles = self.provider.fetch_candles(
                product_id,
                granularity,
                timestamp,
                min(timestamp + step, ensure_utc(end)),
            )
            repaired = self.store.merge(repaired, new_candles)

        self.store.save(repaired)
        return repaired

    def sync(self, product_id, granularity, start, end):
        end = ensure_utc(end)
        if not self.store.exists():
            return self.seed_history(product_id, granularity, start, end)

        candles = self.update_history(product_id, granularity, end)
        return self.repair_gaps(product_id, granularity, end)
