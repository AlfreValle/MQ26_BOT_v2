"""
Clase base para todas las estrategias del bot.
Toda estrategia hereda de BaseStrategy e implementa generate_signals().
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import pandas as pd


class SignalDirection(Enum):
    LONG  = auto()
    SHORT = auto()
    NONE  = auto()


@dataclass
class Signal:
    """Señal de trading completa emitida por una estrategia."""
    strategy_id: str          # e.g. "S01_LondonKillzone"
    symbol: str               # e.g. "EURUSD"
    direction: SignalDirection
    entry_price: float
    sl_price: float           # Stop Loss absoluto
    tp1_price: float          # Take Profit 1 (parcial 50%)
    tp2_price: float          # Take Profit 2 (objetivo extendido)
    timestamp: pd.Timestamp
    timeframe: str            # "M5" | "H1" | etc.
    confidence: float = 1.0  # 0.0–1.0 (escalar size)
    notes: str = ""
    r_r_ratio: float = field(init=False, default=0.0)
    risk_pips: float = field(init=False, default=0.0)

    def __post_init__(self):
        if self.direction in (SignalDirection.LONG, SignalDirection.SHORT):
            if self.direction == SignalDirection.LONG:
                self.risk_pips  = self.entry_price - self.sl_price
                reward_pips     = self.tp1_price - self.entry_price
            else:
                self.risk_pips  = self.sl_price - self.entry_price
                reward_pips     = self.entry_price - self.tp1_price

            self.r_r_ratio = reward_pips / self.risk_pips if self.risk_pips > 0 else 0.0

    @property
    def is_valid(self) -> bool:
        """Una señal es válida si tiene R:R >= 1.5 y SL > 0."""
        return (
            self.direction != SignalDirection.NONE
            and self.risk_pips > 0
            and self.r_r_ratio >= 1.5
        )

    def __repr__(self) -> str:
        d = "LONG" if self.direction == SignalDirection.LONG else "SHORT"
        return (
            f"Signal({self.strategy_id} | {self.symbol} | {d} | "
            f"Entry={self.entry_price:.5f} SL={self.sl_price:.5f} "
            f"TP1={self.tp1_price:.5f} | R:R={self.r_r_ratio:.2f})"
        )


@dataclass
class BacktestTrade:
    """Resultado de un trade en backtesting."""
    signal: Signal
    open_time: pd.Timestamp
    close_time: Optional[pd.Timestamp] = None
    close_price: Optional[float] = None
    pnl_pips: float = 0.0
    pnl_usd: float = 0.0
    outcome: str = "open"    # "tp1" | "tp2" | "sl" | "be" | "manual"
    lot_size: float = 0.01

    @property
    def is_winner(self) -> bool:
        return self.pnl_pips > 0

    @property
    def duration_hours(self) -> float:
        if self.close_time is None:
            return 0.0
        delta = self.close_time - self.open_time
        return delta.total_seconds() / 3600


class BaseStrategy(ABC):
    """
    Clase base para todas las estrategias.

    Cada estrategia debe implementar:
      - generate_signals(): analiza los datos y retorna lista de señales
      - strategy_id: identificador único
      - asset_class: "forex" | "index" | "gold"
    """

    strategy_id: str = "BASE"
    asset_class: str = "forex"
    timeframe_signal: str = "M5"    # TF principal de señales
    timeframe_context: str = "H1"   # TF de contexto/filtros

    # Parámetros por defecto — sobreescribir en subclases
    atr_sl_mult: float = 1.6
    atr_tp1_mult: float = 2.4
    atr_tp2_mult: float = 4.0
    min_rr: float = 1.5

    @abstractmethod
    def generate_signals(
        self,
        df_signal: pd.DataFrame,
        df_context: pd.DataFrame,
        symbol: str,
    ) -> list[Signal]:
        """
        Analiza los datos y retorna señales de trading.

        Args:
            df_signal : DataFrame en el TF de señales (e.g. M5) con indicadores
            df_context: DataFrame en el TF de contexto (e.g. H1) con indicadores
            symbol    : Símbolo del instrumento

        Returns:
            Lista de Signal (puede ser vacía si no hay setups)
        """
        ...

    def _make_long_signal(
        self,
        symbol: str,
        timestamp: pd.Timestamp,
        entry: float,
        sl: float,
        tp1: float,
        tp2: Optional[float] = None,
        confidence: float = 1.0,
        notes: str = "",
    ) -> Signal:
        if tp2 is None:
            tp2 = entry + (tp1 - entry) * 2
        return Signal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=SignalDirection.LONG,
            entry_price=entry,
            sl_price=sl,
            tp1_price=tp1,
            tp2_price=tp2,
            timestamp=timestamp,
            timeframe=self.timeframe_signal,
            confidence=confidence,
            notes=notes,
        )

    def _make_short_signal(
        self,
        symbol: str,
        timestamp: pd.Timestamp,
        entry: float,
        sl: float,
        tp1: float,
        tp2: Optional[float] = None,
        confidence: float = 1.0,
        notes: str = "",
    ) -> Signal:
        if tp2 is None:
            tp2 = entry - (entry - tp1) * 2
        return Signal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=SignalDirection.SHORT,
            entry_price=entry,
            sl_price=sl,
            tp1_price=tp1,
            tp2_price=tp2,
            timestamp=timestamp,
            timeframe=self.timeframe_signal,
            confidence=confidence,
            notes=notes,
        )
