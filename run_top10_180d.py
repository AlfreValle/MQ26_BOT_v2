"""
MQ26 BOT v2 — Validación Top 10 a 180 días (H1)

Corre S03 Asian Range sobre los 10 mejores símbolos del universo IC Markets
usando barras H1 con 6 meses de historia.

Por qué H1: yfinance limita M5 a 60 días. Para 180 días usamos H1 — la lógica
de sesión asiática (00:00–07:00 UTC) y London breakout sigue siendo idéntica,
solo que cada barra representa 1 hora en vez de 5 minutos.

Uso:
    cd MQ26_BOT_v2
    python run_top10_180d.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtester.engine import BacktestEngine, BacktestResult
from backtester.report import generate_html_report, print_comparison_table
from strategies.forex.s03_asian_range import AsianRangeStrategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("top10_180d")

# ─── Top 10 del universo (rankeados por Sharpe en el scan de 60d) ─────────────
TOP10 = [
    "BTCUSD",   # Sharpe 14.93 — mejor del universo
    "EURCAD",   # Sharpe 14.66
    "CHFJPY",   # Sharpe 14.13
    "NZDJPY",   # Sharpe 13.91
    "GBPJPY",   # Sharpe 13.71
    "AUDCAD",   # Sharpe 13.34
    "EURJPY",   # Sharpe 13.32
    "EURUSD",   # Sharpe 12.86
    "AUDUSD",   # Sharpe 12.83
    "XAUUSD",   # Sharpe 12.83
]

PERIOD = "6mo"          # ~180 días de historia
TIMEFRAME = "H1"        # H1 = único TF válido en yfinance para 6mo


def main() -> None:
    logger.info("=" * 65)
    logger.info("  MQ26 BOT v2 — Validación Top 10 | 180 días | H1")
    logger.info("=" * 65)

    all_results: list[BacktestResult] = []

    for symbol in TOP10:
        logger.info(f"\n▶  {symbol} | S03 Asian Range | {PERIOD} | {TIMEFRAME}")
        try:
            # Crear estrategia con H1 como timeframe de señal
            strategy = AsianRangeStrategy()
            strategy.timeframe_signal  = TIMEFRAME
            strategy.timeframe_context = TIMEFRAME

            engine = BacktestEngine(strategy)
            result = engine.run(symbol=symbol, period=PERIOD, use_cache=True)
            all_results.append(result)

        except Exception as e:
            logger.error(f"Error en {symbol}: {e}", exc_info=True)

    if not all_results:
        logger.error("Sin resultados.")
        sys.exit(1)

    print_comparison_table(all_results)
    report_path = generate_html_report(all_results, report_name="top10_180d")
    logger.info(f"\nReporte guardado: {report_path}")


if __name__ == "__main__":
    main()
