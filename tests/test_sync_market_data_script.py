from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

from scripts import sync_market_data


UTC = timezone.utc


def test_latest_completed_daily_candle_open_uses_start_of_current_utc_day():
    now = datetime(2026, 5, 1, 13, 45, tzinfo=UTC)

    assert sync_market_data.latest_completed_daily_candle_open(now) == datetime(
        2026, 5, 1, 0, 0, tzinfo=UTC
    )


def test_main_passes_arguments_to_run_sync(monkeypatch):
    captured = {}

    def fake_run_sync(products, granularity, since, mode, data_root):
        captured["products"] = products
        captured["granularity"] = granularity
        captured["since"] = since
        captured["mode"] = mode
        captured["data_root"] = data_root

    monkeypatch.setattr(sync_market_data, "run_sync", fake_run_sync)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync_market_data.py",
            "--product",
            "BTC-USD",
            "--product",
            "ETH-USD",
            "--granularity",
            "1d",
            "--since",
            "2021-01-01",
            "--mode",
            "repair",
            "--data-root",
            "custom-data",
        ],
    )

    sync_market_data.main()

    assert captured == {
        "products": ["BTC-USD", "ETH-USD"],
        "granularity": "1d",
        "since": datetime(2021, 1, 1, 0, 0, tzinfo=UTC),
        "mode": "repair",
        "data_root": "custom-data",
    }


def test_script_executes_directly():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "sync_market_data.py"
    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Sync historical market candles." in result.stdout
