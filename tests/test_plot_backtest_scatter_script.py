from pathlib import Path

from scripts import plot_backtest_scatter


def test_plot_all_writes_svg_files(tmp_path):
    csv_path = tmp_path / "results.csv"
    csv_path.write_text(
        "\n".join(
            [
                "strategy,strategy_label,symbol,start,end,contributed_usd,invested_usd,ending_cash_usd,ending_value_usd,return_pct,deployment_pct,max_drawdown_pct,trade_count",
                "s1,label1,BTC-USD,2020-01-05,2026-04-26,100,100,0,150,50,100,30,1",
                "s2,label2,ETH-USD,2020-01-05,2026-04-26,100,100,0,140,40,100,35,1",
            ]
        )
    )

    plot_backtest_scatter.plot_all(csv_path, tmp_path)

    assert (tmp_path / "return_vs_drawdown.svg").exists()
    assert (tmp_path / "return_vs_deployment.svg").exists()
    assert "Return vs Max Drawdown" in (tmp_path / "return_vs_drawdown.svg").read_text()
