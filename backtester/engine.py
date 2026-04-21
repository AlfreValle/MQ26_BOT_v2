"""
Motor de Backtesting vectorizado.

Flujo:
  1. Carga datos OHLCV multi-timeframe para cada par
  2. Calcula indicadores técnicos
  3. Ejecuta cada estrategia → genera señales históricas
  4. Simula la ejecución: entrada, gestión de SL/TP, cierre
  5. Calcula métricas de performance
  6. Retorna BacktestResult para el reporter

Modelo de ejecución simplificado (bar-by-bar):
  - Entrada: al open de la vela siguiente a la señal (no lookahead bias)
  - SL/TP: chequeados en cada vela posterior (high/low touch)
  - TP1 parcial (50%): al llegar a TP1 se cierra la mitad y SL se mueve a BE
  - TP2: el 50% restante corre hasta TP2 o SL dinámico
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from config.instruments import Instrument, price_to_pips, ALL_INSTRUMENTS
from config.settings import settings
from core.data_feed import fetch_multi_timeframe
from core.market_structure import add_indicators
from strategies.base import BaseStrategy, Signal, SignalDirection, BacktestTrade
from risk.position_sizer import PortfolioState, PositionSizer, SizingResult

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Resultados completos de un backtest."""
    strategy_id: str
    symbol: str
    period: str
    initial_capital: float
    final_capital: float
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    # Métricas calculadas post-hoc
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win_pips: float = 0.0
    avg_loss_pips: float = 0.0
    avg_rr_actual: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    total_pnl_usd: float = 0.0
    total_pnl_pct: float = 0.0
    avg_trade_duration_h: float = 0.0

    def compute_metrics(self) -> None:
        """Calcula todas las métricas a partir de la lista de trades."""
        closed = [t for t in self.trades if t.outcome != "open"]
        if not closed:
            return

        self.total_trades  = len(closed)
        winners = [t for t in closed if t.pnl_pips > 0]
        losers  = [t for t in closed if t.pnl_pips <= 0]

        self.winning_trades = len(winners)
        self.losing_trades  = len(losers)
        self.win_rate = self.winning_trades / self.total_trades if self.total_trades else 0

        wins_pips  = [t.pnl_pips for t in winners]
        loss_pips  = [abs(t.pnl_pips) for t in losers]

        self.avg_win_pips  = float(np.mean(wins_pips))  if wins_pips  else 0
        self.avg_loss_pips = float(np.mean(loss_pips))  if loss_pips  else 0
        self.avg_rr_actual = self.avg_win_pips / self.avg_loss_pips if self.avg_loss_pips else 0

        gross_profit = sum(t.pnl_usd for t in winners)
        gross_loss   = abs(sum(t.pnl_usd for t in losers))
        self.profit_factor = gross_profit / gross_loss if gross_loss else float("inf")

        self.total_pnl_usd = sum(t.pnl_usd for t in closed)
        self.total_pnl_pct = self.total_pnl_usd / self.initial_capital * 100

        self.avg_trade_duration_h = float(np.mean([t.duration_hours for t in closed]))

        # Drawdown desde equity curve
        if self.equity_curve:
            eq = np.array(self.equity_curve)
            peak = np.maximum.accumulate(eq)
            dd   = (peak - eq) / peak
            self.max_drawdown_pct = float(dd.max() * 100)

        # Sharpe ratio anualizado (daily returns del equity curve)
        if len(self.equity_curve) > 10:
            eq = np.array(self.equity_curve)
            daily_ret = np.diff(eq) / eq[:-1]
            if daily_ret.std() > 0:
                self.sharpe_ratio = float(
                    (daily_ret.mean() / daily_ret.std()) * np.sqrt(252)
                )

    def summary(self) -> str:
        lines = [
            f"{'='*60}",
            f"  BACKTEST: {self.strategy_id} | {self.symbol} | {self.period}",
            f"{'='*60}",
            f"  Capital inicial:  ${self.initial_capital:>10,.2f}",
            f"  Capital final:    ${self.final_capital:>10,.2f}",
            f"  PnL Total:        ${self.total_pnl_usd:>+10,.2f}  ({self.total_pnl_pct:+.2f}%)",
            f"{'-'*60}",
            f"  Trades totales:   {self.total_trades:>4}",
            f"  Ganadores:        {self.winning_trades:>4}  ({self.win_rate:.1%})",
            f"  Perdedores:       {self.losing_trades:>4}",
            f"  Avg Win (pips):   {self.avg_win_pips:>8.1f}",
            f"  Avg Loss (pips):  {self.avg_loss_pips:>8.1f}",
            f"  R:R Real:         {self.avg_rr_actual:>8.2f}",
            f"  Profit Factor:    {self.profit_factor:>8.2f}",
            f"  Max Drawdown:     {self.max_drawdown_pct:>7.2f}%",
            f"  Sharpe Ratio:     {self.sharpe_ratio:>8.2f}",
            f"  Duracion avg:     {self.avg_trade_duration_h:>7.1f}h",
            f"{'='*60}",
        ]
        return "\n".join(lines)


class BacktestEngine:
    """
    Motor de backtesting bar-by-bar para cualquier estrategia.
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: float | None = None,
        commission_per_lot: float | None = None,
        slippage_pips: float | None = None,
        time_exit_hours: float = 8.0,   # #2 Cerrar si no llega a TP1 en N horas
    ):
        self.strategy = strategy
        self.initial_capital = initial_capital or settings.backtest.initial_capital
        self.commission_per_lot = commission_per_lot or settings.backtest.commission_per_lot
        self.slippage_pips = slippage_pips or settings.backtest.slippage_pips
        self.time_exit_hours = time_exit_hours  # #2

    def run(
        self,
        symbol: str,
        period: str = "auto",
        use_cache: bool = True,
    ) -> BacktestResult:
        """
        Ejecuta el backtest completo para un símbolo.

        Args:
            symbol : Símbolo MT5/yfinance (e.g. "EURUSD")
            period : Período de datos ("60d", "2y", "auto")
            use_cache: Usar caché de datos

        Returns:
            BacktestResult con todas las métricas
        """
        logger.info(f"Iniciando backtest: {self.strategy.strategy_id} | {symbol}")

        # 1. Cargar datos multi-timeframe
        timeframes = [self.strategy.timeframe_context, self.strategy.timeframe_signal]
        data = fetch_multi_timeframe(symbol, timeframes=list(set(timeframes)), use_cache=use_cache)

        tf_sig = self.strategy.timeframe_signal
        tf_ctx = self.strategy.timeframe_context

        if tf_sig not in data or tf_ctx not in data:
            logger.error(f"No se pudo cargar datos para {symbol}")
            return BacktestResult(
                strategy_id=self.strategy.strategy_id,
                symbol=symbol,
                period=period,
                initial_capital=self.initial_capital,
                final_capital=self.initial_capital,
            )

        df_signal  = add_indicators(data[tf_sig])
        df_context = add_indicators(data[tf_ctx])

        # 2. Generar señales
        logger.info(f"Generando señales...")
        signals = self.strategy.generate_signals(df_signal, df_context, symbol)
        logger.info(f"Señales generadas: {len(signals)}")

        if not signals:
            logger.warning(f"Sin señales para {symbol} con {self.strategy.strategy_id}")
            return BacktestResult(
                strategy_id=self.strategy.strategy_id,
                symbol=symbol,
                period=period,
                initial_capital=self.initial_capital,
                final_capital=self.initial_capital,
            )

        # 3. Simular trades
        instrument = self._get_instrument(symbol)
        trades, equity_curve = self._simulate_trades(
            signals, df_signal, instrument
        )

        # 4. Construir resultado
        final_capital = equity_curve[-1] if equity_curve else self.initial_capital
        result = BacktestResult(
            strategy_id=self.strategy.strategy_id,
            symbol=symbol,
            period=period,
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            trades=trades,
            equity_curve=equity_curve,
        )
        result.compute_metrics()

        logger.info(f"\n{result.summary()}")
        return result

    def _simulate_trades(
        self,
        signals: list[Signal],
        df: pd.DataFrame,
        instrument: Instrument,
    ) -> tuple[list[BacktestTrade], list[float]]:
        """
        Simula la ejecución bar-by-bar con gestión de SL/TP.
        Modelo v4 — #1 TP3 + #2 Time Exit:
          - Entrada al open de la vela siguiente a la señal
          - TP1 (33%): cierra 1/3, SL mueve a breakeven
          - TP2 (33%): cierra otro 1/3, trailing sigue activo
          - TP3 ilimitado (34%): corre indefinidamente con trailing ATR
          - Time Exit (#2): si no llega a TP1 en time_exit_hours → cerrar al mercado
          - SL: stop total si price toca el nivel
        """
        trades: list[BacktestTrade] = []
        equity = self.initial_capital
        equity_curve = [equity]
        pip_size = instrument.pip_size

        for signal in signals:
            # Encontrar el index de la barra de señal
            try:
                sig_loc = df.index.get_loc(signal.timestamp)
            except KeyError:
                # Buscar la barra más cercana
                diffs = abs(df.index - signal.timestamp)
                sig_loc = diffs.argmin()

            # Entrada al open de la siguiente barra
            entry_loc = sig_loc + 1
            if entry_loc >= len(df):
                continue

            entry_bar = df.iloc[entry_loc]
            entry_price = entry_bar["open"]

            # Ajustar por slippage
            slip = self.slippage_pips * pip_size
            if signal.direction == SignalDirection.LONG:
                entry_price += slip
            else:
                entry_price -= slip

            # Calcular lot size (simplificado para backtesting)
            risk_usd = equity * (settings.risk.risk_per_trade_pct / 100)
            sl_pips  = price_to_pips(instrument, abs(signal.risk_pips))
            if sl_pips <= 0:
                continue

            # Usar pip_value_usd real del instrumento (corrige JPY, MXN, etc.)
            pip_val_per_lot = instrument.pip_value_usd
            lot_size = risk_usd / (sl_pips * pip_val_per_lot)
            lot_size = max(instrument.min_lot, round(lot_size / instrument.lot_step) * instrument.lot_step)

            # Crear trade
            trade = BacktestTrade(
                signal=signal,
                open_time=df.index[entry_loc],
                lot_size=lot_size,
            )

            # ── ATR para trailing stop ─────────────────────────────────────────
            entry_atr = entry_bar.get("atr_14", 0) or 0
            trailing_atr_mult = 0.8   # 0.8x ATR tras TP1

            # ── Porciones de posición — #1 TP3: 33% / 33% / 34% ──────────────
            TP1_FRAC = 0.33   # Cerrar en TP1
            TP2_FRAC = 0.33   # Cerrar en TP2
            # El 34% restante corre con trailing ilimitado (sin TP3 fijo)

            # ── Estado del trade ──────────────────────────────────────────────
            sl_current        = signal.sl_price
            tp1_hit           = False
            tp2_hit           = False
            size_remaining    = 1.0
            pnl_usd_accum     = 0.0   # PnL acumulado de cierres parciales
            pnl_pips_accum    = 0.0
            open_ts           = df.index[entry_loc]

            # Seguimiento del peak/trough para trailing
            peak_price_long    = entry_price
            trough_price_short = entry_price

            for future_loc in range(entry_loc + 1, min(entry_loc + 1000, len(df))):
                bar    = df.iloc[future_loc]
                bar_ts = df.index[future_loc]

                high = bar["high"]
                low  = bar["low"]

                # ── #2 Time-based exit: cerrar si no llega a TP1 en N horas ──
                if not tp1_hit:
                    elapsed_h = (bar_ts - open_ts).total_seconds() / 3600
                    if elapsed_h >= self.time_exit_hours:
                        close_price = bar["open"]
                        if signal.direction == SignalDirection.LONG:
                            pnl_pips = price_to_pips(instrument, close_price - entry_price)
                        else:
                            pnl_pips = price_to_pips(instrument, entry_price - close_price)
                        pnl_usd = pnl_pips * pip_val_per_lot * lot_size
                        pnl_usd -= self.commission_per_lot * lot_size
                        trade.close_time  = bar_ts
                        trade.close_price = close_price
                        trade.pnl_pips    = pnl_pips
                        trade.pnl_usd     = pnl_usd
                        trade.outcome     = "time_exit"
                        equity += pnl_usd
                        equity_curve.append(equity)
                        break

                if signal.direction == SignalDirection.LONG:
                    # ── TP1: cerrar 33% ───────────────────────────────────────
                    if not tp1_hit and high >= signal.tp1_price:
                        tp1_pips    = price_to_pips(instrument, signal.tp1_price - entry_price)
                        pnl_tp1     = tp1_pips * pip_val_per_lot * lot_size * TP1_FRAC
                        pnl_tp1    -= self.commission_per_lot * lot_size * TP1_FRAC
                        equity         += pnl_tp1
                        pnl_usd_accum  += pnl_tp1
                        pnl_pips_accum += tp1_pips * TP1_FRAC
                        equity_curve.append(equity)
                        size_remaining  = 1.0 - TP1_FRAC   # 0.67
                        sl_current      = entry_price        # Mover a breakeven
                        tp1_hit         = True
                        peak_price_long = max(peak_price_long, signal.tp1_price)

                    # ── TP2: cerrar otro 33% ──────────────────────────────────
                    if tp1_hit and not tp2_hit and high >= signal.tp2_price:
                        tp2_pips    = price_to_pips(instrument, signal.tp2_price - entry_price)
                        pnl_tp2     = tp2_pips * pip_val_per_lot * lot_size * TP2_FRAC
                        pnl_tp2    -= self.commission_per_lot * lot_size * TP2_FRAC
                        equity         += pnl_tp2
                        pnl_usd_accum  += pnl_tp2
                        pnl_pips_accum += tp2_pips * TP2_FRAC
                        equity_curve.append(equity)
                        size_remaining  = 1.0 - TP1_FRAC - TP2_FRAC   # 0.34
                        tp2_hit         = True
                        peak_price_long = max(peak_price_long, signal.tp2_price)

                    # ── Trailing ATR: actualizar peak y ajustar SL ────────────
                    if tp1_hit and entry_atr > 0:
                        if high > peak_price_long:
                            peak_price_long = high
                        trailing_sl = peak_price_long - entry_atr * trailing_atr_mult
                        sl_current  = max(sl_current, trailing_sl)

                    # ── SL / trailing cierra la posición restante ─────────────
                    if low <= sl_current:
                        close_price = sl_current
                        pnl_pips    = price_to_pips(instrument, close_price - entry_price)
                        pnl_usd     = pnl_pips * pip_val_per_lot * lot_size * size_remaining
                        pnl_usd    -= self.commission_per_lot * lot_size * size_remaining
                        trade.close_time  = bar_ts
                        trade.close_price = close_price
                        trade.pnl_pips    = pnl_pips_accum + pnl_pips * size_remaining
                        trade.pnl_usd     = pnl_usd_accum + pnl_usd
                        trade.outcome     = "sl" if not tp1_hit else "trail"
                        equity += pnl_usd
                        equity_curve.append(equity)
                        break

                else:  # SHORT
                    # ── TP1: cerrar 33% ───────────────────────────────────────
                    if not tp1_hit and low <= signal.tp1_price:
                        tp1_pips    = price_to_pips(instrument, entry_price - signal.tp1_price)
                        pnl_tp1     = tp1_pips * pip_val_per_lot * lot_size * TP1_FRAC
                        pnl_tp1    -= self.commission_per_lot * lot_size * TP1_FRAC
                        equity           += pnl_tp1
                        pnl_usd_accum    += pnl_tp1
                        pnl_pips_accum   += tp1_pips * TP1_FRAC
                        equity_curve.append(equity)
                        size_remaining    = 1.0 - TP1_FRAC
                        sl_current        = entry_price
                        tp1_hit           = True
                        trough_price_short = min(trough_price_short, signal.tp1_price)

                    # ── TP2: cerrar otro 33% ──────────────────────────────────
                    if tp1_hit and not tp2_hit and low <= signal.tp2_price:
                        tp2_pips    = price_to_pips(instrument, entry_price - signal.tp2_price)
                        pnl_tp2     = tp2_pips * pip_val_per_lot * lot_size * TP2_FRAC
                        pnl_tp2    -= self.commission_per_lot * lot_size * TP2_FRAC
                        equity           += pnl_tp2
                        pnl_usd_accum    += pnl_tp2
                        pnl_pips_accum   += tp2_pips * TP2_FRAC
                        equity_curve.append(equity)
                        size_remaining    = 1.0 - TP1_FRAC - TP2_FRAC
                        tp2_hit           = True
                        trough_price_short = min(trough_price_short, signal.tp2_price)

                    # ── Trailing ATR: actualizar trough y ajustar SL ──────────
                    if tp1_hit and entry_atr > 0:
                        if low < trough_price_short:
                            trough_price_short = low
                        trailing_sl = trough_price_short + entry_atr * trailing_atr_mult
                        sl_current  = min(sl_current, trailing_sl)

                    # ── SL / trailing cierra la posición restante ─────────────
                    if high >= sl_current:
                        close_price = sl_current
                        pnl_pips    = price_to_pips(instrument, entry_price - close_price)
                        pnl_usd     = pnl_pips * pip_val_per_lot * lot_size * size_remaining
                        pnl_usd    -= self.commission_per_lot * lot_size * size_remaining
                        trade.close_time  = bar_ts
                        trade.close_price = close_price
                        trade.pnl_pips    = pnl_pips_accum + pnl_pips * size_remaining
                        trade.pnl_usd     = pnl_usd_accum + pnl_usd
                        trade.outcome     = "sl" if not tp1_hit else "trail"
                        equity += pnl_usd
                        equity_curve.append(equity)
                        break

            else:
                # Trade aún abierto al final del período
                last_bar = df.iloc[-1]
                close_price = last_bar["close"]
                if signal.direction == SignalDirection.LONG:
                    pnl_pips = price_to_pips(instrument, close_price - entry_price)
                else:
                    pnl_pips = price_to_pips(instrument, entry_price - close_price)
                pnl_usd = pnl_pips * pip_val_per_lot * lot_size * size_remaining
                trade.close_time  = df.index[-1]
                trade.close_price = close_price
                trade.pnl_pips    = pnl_pips
                trade.pnl_usd     = pnl_usd
                trade.outcome     = "manual"
                equity += pnl_usd
                equity_curve.append(equity)

            trades.append(trade)

        return trades, equity_curve

    def _get_instrument(self, symbol: str) -> Instrument:
        """Obtiene el instrumento o usa un fallback genérico."""
        from config.instruments import get_instrument
        try:
            return get_instrument(symbol)
        except KeyError:
            from config.instruments import Instrument
            return Instrument(
                symbol=symbol, yf_symbol=symbol + "=X",
                asset_class="forex", pip_size=0.0001,
                spread_typical=1.0,
            )
