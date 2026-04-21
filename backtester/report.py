"""
Generador de reportes de backtesting.
Produce HTML interactivo con Plotly + resumen CSV.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backtester.engine import BacktestResult

logger = logging.getLogger(__name__)
REPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def generate_html_report(
    results: list[BacktestResult],
    report_name: str = "backtest_report",
) -> Path:
    """
    Genera un reporte HTML con Plotly para una lista de resultados.
    Con muchos símbolos divide en páginas de 10 para evitar spacing overflow.
    """
    # Filtrar resultados sin trades
    valid = [r for r in results if r.total_trades > 0]
    if not valid:
        valid = results

    # Ordenar por Sharpe descendente
    valid = sorted(valid, key=lambda r: r.sharpe_ratio, reverse=True)

    PAGE_SIZE = 10  # máximo subplots por figura
    pages = [valid[i:i + PAGE_SIZE] for i in range(0, len(valid), PAGE_SIZE)]
    report_paths = []

    for page_num, page_results in enumerate(pages, start=1):
        n = len(page_results)
        # Espaciado dinámico: mínimo 0.02, máximo 0.06
        v_spacing = max(0.02, min(0.06, 0.5 / max(n, 1)))

        fig = make_subplots(
            rows=n,
            cols=2,
            subplot_titles=[
                title
                for r in page_results
                for title in [
                    f"{r.strategy_id} | {r.symbol} — Equity Curve",
                    f"{r.strategy_id} | {r.symbol} — Distribución PnL",
                ]
            ],
            vertical_spacing=v_spacing,
            horizontal_spacing=0.08,
        )

        for row_idx, result in enumerate(page_results, start=1):
            _add_equity_curve(fig, result, row=row_idx, col=1)
            _add_pnl_distribution(fig, result, row=row_idx, col=2)

        suffix = f"_p{page_num}" if len(pages) > 1 else ""
        fig.update_layout(
            title_text=f"MQ26 BOT v2 — Backtest Report{suffix} (top {PAGE_SIZE*(page_num-1)+1}–{PAGE_SIZE*page_num})",
            height=340 * n,
            template="plotly_dark",
            showlegend=False,
            font=dict(family="Consolas, monospace", size=11),
        )

        rname = f"{report_name}{suffix}"
        report_path = REPORT_DIR / f"{rname}.html"
        fig.write_html(str(report_path))
        logger.info(f"Reporte HTML guardado: {report_path}")
        report_paths.append(report_path)

    # CSV de trades
    _export_trades_csv(results, report_name)

    return report_paths[0]


def _add_equity_curve(fig: go.Figure, result: BacktestResult, row: int, col: int) -> None:
    if not result.equity_curve:
        return

    eq = result.equity_curve
    x  = list(range(len(eq)))

    # Colores según rendimiento
    color = "#00C896" if eq[-1] >= eq[0] else "#FF4B4B"

    # Equity curve
    fig.add_trace(
        go.Scatter(
            x=x, y=eq,
            mode="lines",
            line=dict(color=color, width=2),
            name="Equity",
            hovertemplate="Trade #%{x}<br>Equity: $%{y:,.2f}",
        ),
        row=row, col=col,
    )

    # Línea de capital inicial
    fig.add_hline(
        y=result.initial_capital,
        line_dash="dot",
        line_color="#888888",
        row=row, col=col,
    )

    # Anotación con métricas clave
    metrics_text = (
        f"Win Rate: {result.win_rate:.1%} | "
        f"PF: {result.profit_factor:.2f} | "
        f"Sharpe: {result.sharpe_ratio:.2f} | "
        f"MaxDD: {result.max_drawdown_pct:.1f}%"
    )
    fig.add_annotation(
        text=metrics_text,
        xref="paper", yref="paper",
        x=0.5, y=1.02,
        showarrow=False,
        font=dict(size=10, color="#CCCCCC"),
        row=row, col=col,
    )


def _add_pnl_distribution(fig: go.Figure, result: BacktestResult, row: int, col: int) -> None:
    closed = [t for t in result.trades if t.outcome != "open"]
    if not closed:
        return

    pnls = [t.pnl_pips for t in closed]
    colors = ["#00C896" if p > 0 else "#FF4B4B" for p in pnls]

    fig.add_trace(
        go.Bar(
            x=list(range(len(pnls))),
            y=pnls,
            marker_color=colors,
            name="PnL (pips)",
            hovertemplate="Trade #%{x}<br>PnL: %{y:.1f} pips",
        ),
        row=row, col=col,
    )

    # Línea de 0
    fig.add_hline(y=0, line_color="#888888", line_dash="dot", row=row, col=col)


def _export_trades_csv(results: list[BacktestResult], name: str) -> None:
    all_rows = []
    for r in results:
        for t in r.trades:
            if t.outcome == "open":
                continue
            all_rows.append({
                "strategy":  r.strategy_id,
                "symbol":    r.symbol,
                "direction": t.signal.direction.name,
                "open_time": t.open_time,
                "close_time": t.close_time,
                "entry":     t.signal.entry_price,
                "sl":        t.signal.sl_price,
                "tp1":       t.signal.tp1_price,
                "tp2":       t.signal.tp2_price,
                "lot_size":  t.lot_size,
                "pnl_pips":  t.pnl_pips,
                "pnl_usd":   t.pnl_usd,
                "outcome":   t.outcome,
                "duration_h": t.duration_hours,
                "notes":     t.signal.notes,
            })

    if not all_rows:
        return

    df = pd.DataFrame(all_rows)
    csv_path = REPORT_DIR / f"{name}_trades.csv"
    df.to_csv(csv_path, index=False)
    logger.info(f"CSV de trades exportado: {csv_path}")


def print_comparison_table(results: list[BacktestResult]) -> None:
    """Imprime tabla comparativa de todos los backtests en consola."""
    header = f"{'Strategy':<20} {'Symbol':<8} {'Trades':>6} {'WinRate':>8} {'PF':>6} {'Sharpe':>8} {'MaxDD%':>8} {'PnL%':>8}"
    sep = "-" * len(header)
    print("\n" + "=" * len(header))
    print("  MQ26 BOT v2 - Comparativa de Estrategias")
    print("=" * len(header))
    print(header)
    print(sep)

    for r in results:
        line = (
            f"{r.strategy_id:<20} {r.symbol:<8} "
            f"{r.total_trades:>6} {r.win_rate:>8.1%} "
            f"{r.profit_factor:>6.2f} {r.sharpe_ratio:>8.2f} "
            f"{r.max_drawdown_pct:>8.2f} {r.total_pnl_pct:>+8.2f}%"
        )
        print(line)

    print("=" * len(header))
    print()
