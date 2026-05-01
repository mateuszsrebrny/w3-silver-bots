from decimal import Decimal


class MultiAssetSeries:
    def __init__(self, series_by_symbol):
        self.series_by_symbol = dict(series_by_symbol)

    def symbols(self):
        return list(self.series_by_symbol.keys())

    def common_timestamps_since(self, since):
        timestamp_sets = []
        for series in self.series_by_symbol.values():
            timestamps = {
                candle.timestamp for candle in series.candles_since(since)
            }
            timestamp_sets.append(timestamps)

        if not timestamp_sets:
            return []

        return sorted(set.intersection(*timestamp_sets))

    def common_sunday_timestamps_since(self, since):
        timestamp_sets = []
        for series in self.series_by_symbol.values():
            timestamps = {
                candle.timestamp for candle in series.sunday_candles_since(since)
            }
            timestamp_sets.append(timestamps)

        if not timestamp_sets:
            return []

        return sorted(set.intersection(*timestamp_sets))

    def close(self, symbol, timestamp):
        return self.series_by_symbol[symbol].close_at(timestamp)

    def moving_average(self, symbol, timestamp, window_days):
        return self.series_by_symbol[symbol].moving_average(timestamp, window_days)

    def trailing_return(self, symbol, timestamp, window_days):
        return self.series_by_symbol[symbol].trailing_return(timestamp, window_days)

    def drawdown_from_high(self, symbol, timestamp, window_days):
        return self.series_by_symbol[symbol].drawdown_from_high(timestamp, window_days)

    def symbol_label(self):
        return "+".join(self.symbols())
