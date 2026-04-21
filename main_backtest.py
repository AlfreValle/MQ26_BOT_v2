"""
MQ26 BOT v2 — Runner de Backtesting

Estrategia de producción: S03 Asian Range v3 (Top 8 pares validados)
  S03 + BTCUSD / XAUUSD / AUDUSD / NZDUSD / ETHUSD / GBPUSD / EURUSD / AUDJPY

Uso:
  python main_backtest.py                     # S03 en Top 8 (default)
  python main_backtest.py --strategy s03      # Solo S03 Asian Range
  python main_backtest.py --symbol BTCUSD     # Solo un par
  python main_backtest.py --period 60d        # Últimos 60 días

Ejemplo:
  cd MQ26_BOT_v2
  python main_backtest.py --strategy s03 --period 60d
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Asegurar que el proyecto raíz esté en el path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtester.engine import BacktestEngine, BacktestResult
from backtester.report import generate_html_report, print_comparison_table
from strategies.forex.s03_asian_range import AsianRangeStrategy
# S01, S02 disponibles pero no en producción — PF < S03
# from strategies.forex.s01_london_killzone import LondonKillzoneStrategy
# from strategies.forex.s02_fvg_retest import FVGRetestStrategy
# Índices — disponibles para análisis separado
# from strategies.indices.s04_orb_vwap import ORBVWAPStrategy
# from strategies.indices.s05_vwap_bounce import VWAPBounceStrategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main_backtest")

# ─── Estrategia de producción ─────────────────────────────────────────────────
# Solo S03 Asian Range v3 — validado 60d M5, todos los pares con PF > 1
# S06/S07 Order Block ELIMINADOS: PF 0.54, WR 43%, Sharpe -6.97 (no rentable)

STRATEGIES = {
    "s03": AsianRangeStrategy,   # ← ÚNICA estrategia de producción
}

# Top 8 validados — orden por Sharpe histórico (M136 priority)
TOP8_SYMBOLS = [
    "BTCUSD",   # Sharpe 25.86 | PF 11.79 | WR 91.7% | 24/7
    "XAUUSD",   # Sharpe 16.55 | PF  3.43 | WR 80.0% | Lun-Vie (Oro)
    "AUDUSD",   # Sharpe 12.82 | PF  3.08 | WR 75.0% | Lun-Vie
    "NZDUSD",   # Sharpe 12.76 | PF  2.74 | WR 77.4% | Lun-Vie
    "ETHUSD",   # Sharpe 12.09 | PF  2.55 | WR 86.4% | 24/7
    "GBPUSD",   # Sharpe 10.94 | PF  2.29 | WR 65.1% | Lun-Vie
    "EURUSD",   # Sharpe  9.95 | PF  2.07 | WR 65.0% | Lun-Vie
    "AUDJPY",   # Sharpe  8.45 | PF  1.46 | WR 59.1% | Lun-Vie
]

STRATEGY_PAIRS = {
    # S03 default = Top 8 producción (todos PF > 1 y Sharpe > 8)
    "s03": TOP8_SYMBOLS,
}

DEFAULT_PERIOD = "60d"   # Máximo disponible en M5 con yfinance


def run_backtest(
    strategy_key: str,
    symbol: str,
    period: str = DEFAULT_PERIOD,
    capital: float | None = None,
) -> BacktestResult:
    """Ejecuta un backtest individual y retorna el resultado."""
    StrategyClass = STRATEGIES[strategy_key]
    strategy = StrategyClass()
    engine = BacktestEngine(strategy, initial_capital=capital)
    return engine.run(symbol=symbol, period=period, use_cache=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MQ26 BOT v2 — Backtest de estrategias institucionales",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--strategy", "-s",
        choices=list(STRATEGIES.keys()) + ["all"],
        default="s03",
        help="Estrategia a backtestear (default: s03 — Asian Range v3)",
    )
    parser.add_argument(
        "--symbol", "-p",
        default=None,
        help="Par de divisas (default: pares recomendados por estrategia)",
    )
    parser.add_argument(
        "--period",
        default=DEFAULT_PERIOD,
        help=f"Período de datos yfinance (default: {DEFAULT_PERIOD})",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="No usar caché de datos (fuerza nueva descarga)",
    )
    parser.add_argument(
        "--report-name",
        default="backtest_report",
        help="Nombre del archivo de reporte HTML",
    )
    parser.add_argument(
        "--capital", "-c",
        type=float,
        default=None,
        help="Capital inicial para el backtest (default: valor en settings.py)",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  MQ26 BOT v2 — Backtesting Engine")
    logger.info("=" * 60)

    # Determinar qué estrategias y pares correr
    if args.strategy == "all":
        strategies_to_run = list(STRATEGIES.keys())
    else:
        strategies_to_run = [args.strategy]

    all_results: list[BacktestResult] = []

    for strat_key in strategies_to_run:
        pairs = [args.symbol] if args.symbol else STRATEGY_PAIRS[strat_key]

        for pair in pairs:
            logger.info(f"\n▶ Backtest: {strat_key.upper()} | {pair} | {args.period}")
            try:
                result = run_backtest(
                    strategy_key=strat_key,
                    symbol=pair,
                    period=args.period,
                    capital=args.capital,
                )
                all_results.append(result)
            except Exception as e:
                logger.error(f"Error en backtest {strat_key}/{pair}: {e}", exc_info=True)

    if not all_results:
        logger.error("No se produjeron resultados. Verifica la conexión y los datos.")
        sys.exit(1)

    # Mostrar tabla comparativa
    print_comparison_table(all_results)

    # Generar reporte HTML
    report_path = generate_html_report(all_results, report_name=args.report_name)
    logger.info(f"\n✓ Reporte generado: {report_path}")
    logger.info("  Abrí el archivo HTML en tu navegador para ver los gráficos interactivos.")


if __name__ == "__main__":
    main()
