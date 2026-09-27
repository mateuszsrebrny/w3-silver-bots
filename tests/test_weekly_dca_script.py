from decimal import Decimal
import sys

import pytest

from scripts import weekly_dca


def test_parse_args_defaults_to_preview(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weekly_dca.py",
            "--adai",
            "300",
            "--wbtc",
            "123.98",
            "--wsteth",
            "176.02",
        ],
    )

    args = weekly_dca.parse_args()

    assert args.execute is False
    assert args.adai == Decimal("300")
    assert args.wbtc == Decimal("123.98")
    assert args.wsteth == Decimal("176.02")


def test_parse_args_defaults_adai_to_zero(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weekly_dca.py",
            "--wbtc",
            "123.98",
            "--wsteth",
            "176.02",
        ],
    )

    args = weekly_dca.parse_args()

    assert args.adai == Decimal("0")
    assert args.wbtc == Decimal("123.98")
    assert args.wsteth == Decimal("176.02")


def test_parse_args_accepts_zero_adai(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weekly_dca.py",
            "--adai",
            "0",
            "--wbtc",
            "123.98",
            "--wsteth",
            "176.02",
        ],
    )

    args = weekly_dca.parse_args()

    assert args.adai == Decimal("0")


def test_parse_args_rejects_negative_adai(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "weekly_dca.py",
            "--adai",
            "-1",
            "--wbtc",
            "123.98",
            "--wsteth",
            "176.02",
        ],
    )

    with pytest.raises(SystemExit):
        weekly_dca.parse_args()


def test_build_commands_preview():
    args = type(
        "Args",
        (),
        {
            "adai": Decimal("300"),
            "wbtc": Decimal("123.98"),
            "wsteth": Decimal("176.02"),
            "execute": False,
            "yes": False,
            "python": "python",
        },
    )()

    commands = weekly_dca.build_commands(args)

    assert commands[0][-1:] == ["--preview"]
    assert commands[0][0] == "python"
    assert commands[0][1].endswith("scripts/aave_withdraw.py")
    assert commands[0][2:] == ["--token", "adai", "--amount", "300", "--preview"]
    assert commands[1][1].endswith("scripts/trade.py")
    assert commands[1][2:] == [
        "--from-token",
        "dai",
        "--to-token",
        "wbtc",
        "--amount",
        "123.98",
        "--preview",
        "--assume-input-balance",
        "300",
    ]
    assert commands[2][2:] == [
        "--from-token",
        "dai",
        "--to-token",
        "wsteth",
        "--amount",
        "176.02",
        "--preview",
        "--assume-input-balance",
        "176.02",
    ]


def test_build_commands_skips_zero_adai_withdraw():
    args = type(
        "Args",
        (),
        {
            "adai": Decimal("0"),
            "wbtc": Decimal("123.98"),
            "wsteth": Decimal("176.02"),
            "execute": False,
            "yes": False,
            "python": "python",
        },
    )()

    commands = weekly_dca.build_commands(args)

    assert len(commands) == 2
    assert all("aave_withdraw.py" not in command[1] for command in commands)
    assert commands[0][1].endswith("scripts/trade.py")
    assert commands[0][2:] == [
        "--from-token",
        "dai",
        "--to-token",
        "wbtc",
        "--amount",
        "123.98",
        "--preview",
    ]
    assert commands[1][2:] == [
        "--from-token",
        "dai",
        "--to-token",
        "wsteth",
        "--amount",
        "176.02",
        "--preview",
    ]


def test_build_commands_execute_yes():
    args = type(
        "Args",
        (),
        {
            "adai": Decimal("300"),
            "wbtc": Decimal("123.98"),
            "wsteth": Decimal("176.02"),
            "execute": True,
            "yes": True,
            "python": "python",
        },
    )()

    commands = weekly_dca.build_commands(args)

    assert commands[0][-2:] == ["--execute", "--yes"]
    assert commands[1][-2:] == ["--execute", "--yes"]
    assert commands[2][-2:] == ["--execute", "--yes"]


def test_run_commands_stops_on_failure(monkeypatch):
    calls = []

    def fake_run(command, cwd, check):
        calls.append((command, cwd, check))
        if len(calls) == 2:
            raise RuntimeError("boom")

    monkeypatch.setattr(weekly_dca.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError):
        weekly_dca.run_commands([["one"], ["two"], ["three"]])

    assert [call[0] for call in calls] == [["one"], ["two"]]
