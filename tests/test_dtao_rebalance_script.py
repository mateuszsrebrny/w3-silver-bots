import csv
from datetime import date, timedelta

from scripts import run_dtao_rebalance


def test_cli_compares_basket_sizes_with_common_starting_capital(tmp_path, monkeypatch, capsys):
    prices = tmp_path / "prices.csv"
    emissions = tmp_path / "emissions"
    emissions.mkdir()
    entry = date(2025, 3, 2)
    with prices.open("w", newline="") as target:
        writer = csv.DictWriter(
            target, fieldnames=("date", "netuid", "registered_at", "price_tao_per_alpha")
        )
        writer.writeheader()
        for offset in range(3):
            for netuid in (1, 2):
                writer.writerow({
                    "date": (entry + timedelta(days=offset)).isoformat(),
                    "netuid": netuid,
                    "registered_at": netuid * 10,
                    "price_tao_per_alpha": "1",
                })
    for offset in (-1, 0, 1):
        day = entry + timedelta(days=offset)
        with (emissions / f"{day}.csv").open("w", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=("date", "netuid", "registered_at", "tao_in_emission_rao"),
            )
            writer.writeheader()
            for netuid, emission in ((1, 200), (2, 100)):
                writer.writerow({
                    "date": day.isoformat(), "netuid": netuid,
                    "registered_at": netuid * 10,
                    "tao_in_emission_rao": emission,
                })
    monkeypatch.setattr("sys.argv", [
        "run_dtao_rebalance.py", "--prices", str(prices), "--emissions", str(emissions),
        "--window-days", "3", "--basket-size", "2", "--compare-size", "1",
        "--total-tao", "4", "--cadence", "daily",
    ])
    run_dtao_rebalance.main()
    output = capsys.readouterr().out
    assert "Top 2; initial 4 TAO; 2 TAO per subnet" in output
    assert "Pure swap top 2 vs top 1: wins 0/1" in output
