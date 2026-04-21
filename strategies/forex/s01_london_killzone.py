"""
ESTRATEGIA 1 — London Killzone Sweep & Reverse (ICT Order Flow)

Concepto: Los market makers barren los stops del rango asiático (Judas Swing)
entre 07:00–09:00 UTC y luego invierten en la dirección real.

Señales:
  LONG:  Sweep del LOW asiático → reversión alcista en M5
  SHORT: Sweep del HIGH asiático → reversión bajista en M5

Mejor en: EURUSD, GBPUSD, GBPJPY
Timeframe: M5 (señal) + H1 (rango asiático)
Sesión:    London Killzone 07:00–10:00 UTC
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from core.sessions import get_asian_range, is_london_killzone
from core.market_structure import detect_engulfing, add_indicators
from strategies.base import BaseStrategy, Signal, SignalDirection

logger = logging.getLogger(__name__)


class LondonKillzoneStrategy(BaseStrategy):
    strategy_id = "S01_LondonKZ"
    asset_class = "forex"
    timeframe_signal  = "M5"
    timeframe_context = "H1"

    # Parámetros ajustables
    atr_sl_mult: float = 1.6
    atr_tp1_mult: float = 2.4
    atr_tp2_mult: float = 4.0
    sweep_buffer_pct: float = 0.0003   # 0.03% bajo/sobre el rango para confirmar sweep
    rsi_reversal_long: float = 40.0    # RSI debe estar bajo 40 (oversold real)
    rsi_reversal_short: float = 60.0   # RSI debe estar sobre 60 (overbought real)
    min_asian_range_pips: int = 20     # Rango asiático mínimo para operar
    max_spread_pips: float = 4.0       # No operar si spread > 4 pips (cubre JPY crosses)
    require_trend_align: bool = True   # Filtrar contra tendencia SMA50 en H1

    def generate_signals(
        self,
        df_signal: pd.DataFrame,   # M5 con indicadores
        df_context: pd.DataFrame,  # H1 con indicadores
        symbol: str,
    ) -> list[Signal]:
        """
        Itera las barras M5 dentro de la London Killzone y busca setups.
        En backtesting se procesan barras históricas; en live solo la última.
        """
        if df_signal.empty or df_context.empty:
            return []

        signals: list[Signal] = []
        dates = df_signal.index.normalize().unique()

        for date in dates:
            day_signals = self._process_day(
                df_signal, df_context, symbol, date
            )
            signals.extend(day_signals)

        return signals

    def _process_day(
        self,
        df_m5: pd.DataFrame,
        df_h1: pd.DataFrame,
        symbol: str,
        date: pd.Timestamp,
    ) -> list[Signal]:
        """Procesa un día completo buscando setups de London KZ."""
        signals: list[Signal] = []

        # 1. Calcular rango asiático del día
        asian = get_asian_range(df_h1, date)
        if asian is None:
            return []

        ar_range = asian["high"] - asian["low"]
        # Detectar pip_size según si es par JPY (cotización en YEN)
        pip_size = 0.01 if "JPY" in symbol else 0.0001
        ar_pips = ar_range / pip_size
        if ar_pips < self.min_asian_range_pips:
            return []

        ah = asian["high"]
        al = asian["low"]

        # 2. Tendencia H1 en el momento del Killzone (SMA50 como filtro)
        h1_before_kz = df_h1[df_h1.index.date == date.date()]
        h1_trend = "neutral"
        if not h1_before_kz.empty and "sma_50" in h1_before_kz.columns:
            last_h1 = h1_before_kz.iloc[-1]
            if last_h1["close"] > last_h1.get("sma_50", last_h1["close"]):
                h1_trend = "bullish"
            else:
                h1_trend = "bearish"

        # 3. Filtrar barras M5 dentro de London Killzone (07:00–10:00 UTC)
        day_str = date.strftime("%Y-%m-%d")
        kz_start = pd.Timestamp(f"{day_str} 07:00:00", tz="UTC")
        kz_end   = pd.Timestamp(f"{day_str} 10:00:00", tz="UTC")

        mask = (df_m5.index >= kz_start) & (df_m5.index < kz_end)
        df_kz = df_m5[mask].copy()

        if len(df_kz) < 3:
            return []

        # 4. Buscar sweeps + reversiones
        setup_long_done  = False
        setup_short_done = False

        for i in range(1, len(df_kz) - 1):
            bar     = df_kz.iloc[i]
            bar_idx = df_kz.index[i]

            # Filtro de spread: aproximar con ATR * factor
            atr = bar.get("atr_14", 0)
            pip_size = 0.01 if "JPY" in symbol else 0.0001
            est_spread_pips = (atr * 0.15) / pip_size  # estimado conservador
            if est_spread_pips > self.max_spread_pips:
                continue

            # Solo 1 setup por dirección por día
            # SETUP LONG: precio barrió el LOW asiático y revirtió
            if not setup_long_done:
                # Filtro tendencia: long solo si H1 es alcista o neutral
                if not self.require_trend_align or h1_trend != "bearish":
                    signal = self._check_long_setup(
                        df_kz, i, bar, bar_idx, al, ah, symbol
                    )
                    if signal and signal.is_valid:
                        signals.append(signal)
                        setup_long_done = True

            # SETUP SHORT: precio barrió el HIGH asiático y revirtió
            if not setup_short_done:
                # Filtro tendencia: short solo si H1 es bajista o neutral
                if not self.require_trend_align or h1_trend != "bullish":
                    signal = self._check_short_setup(
                        df_kz, i, bar, bar_idx, al, ah, symbol
                    )
                    if signal and signal.is_valid:
                        signals.append(signal)
                        setup_short_done = True

        return signals

    def _check_long_setup(
        self,
        df: pd.DataFrame,
        i: int,
        bar: pd.Series,
        ts: pd.Timestamp,
        al: float,
        ah: float,
        symbol: str,
    ) -> Optional[Signal]:
        """
        LONG: La vela anterior (o esta) barrió el low asiático.
        La vela actual es una vela de reversión alcista.
        """
        prev = df.iloc[i - 1]

        # Condición 1: La vela previa penetró el low asiático (sweep)
        sweep_level = al * (1 - self.sweep_buffer_pct)
        if prev["low"] > al and bar["low"] > al:
            return None  # No hubo sweep todavía

        # Alguna de las dos velas tocó el low
        swept = prev["low"] <= sweep_level or bar["low"] <= sweep_level
        if not swept:
            return None

        # Condición 2: RSI en zona oversold al momento del sweep
        rsi = bar.get("rsi_14", 50)
        if pd.isna(rsi) or rsi > self.rsi_reversal_long:
            return None

        # Condición 3: Vela de reversión alcista (engulfing o pin bar)
        body_pct = bar.get("body_pct", 0)
        is_bullish_reversal = (
            bar["close"] > bar["open"]  # vela alcista
            and bar["close"] > prev["open"]  # cierre sobre apertura previa
            and body_pct > 0.5  # cuerpo > 50% del rango
        )
        if not is_bullish_reversal:
            return None

        # Cálculo de SL/TP usando ATR
        atr = bar.get("atr_14")
        if pd.isna(atr) or atr <= 0:
            atr = al * 0.001  # fallback: 0.1%

        entry = bar["close"]
        sl    = min(prev["low"], bar["low"]) - (atr * 0.3)
        tp1   = entry + (atr * self.atr_tp1_mult)
        tp2   = entry + (atr * self.atr_tp2_mult)

        # Filtro: TP1 no debe superar el HIGH asiático (resistencia probable)
        # pero si el rango es suficiente, puede superarlo
        confidence = 0.9 if tp1 < ah else 1.0

        return self._make_long_signal(
            symbol=symbol,
            timestamp=ts,
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            confidence=confidence,
            notes=f"LKZ Long | Asian range {al:.5f}–{ah:.5f} | RSI={rsi:.1f}",
        )

    def _check_short_setup(
        self,
        df: pd.DataFrame,
        i: int,
        bar: pd.Series,
        ts: pd.Timestamp,
        al: float,
        ah: float,
        symbol: str,
    ) -> Optional[Signal]:
        """
        SHORT: La vela anterior (o esta) barrió el high asiático.
        La vela actual es una vela de reversión bajista.
        """
        prev = df.iloc[i - 1]

        # Condición 1: sweep del HIGH asiático
        sweep_level = ah * (1 + self.sweep_buffer_pct)
        swept = prev["high"] >= sweep_level or bar["high"] >= sweep_level
        if not swept:
            return None

        # Condición 2: RSI en zona overbought
        rsi = bar.get("rsi_14", 50)
        if pd.isna(rsi) or rsi < self.rsi_reversal_short:
            return None

        # Condición 3: Vela de reversión bajista
        body_pct = bar.get("body_pct", 0)
        is_bearish_reversal = (
            bar["close"] < bar["open"]
            and bar["close"] < prev["open"]
            and body_pct > 0.5
        )
        if not is_bearish_reversal:
            return None

        atr = bar.get("atr_14")
        if pd.isna(atr) or atr <= 0:
            atr = ah * 0.001

        entry = bar["close"]
        sl    = max(prev["high"], bar["high"]) + (atr * 0.3)
        tp1   = entry - (atr * self.atr_tp1_mult)
        tp2   = entry - (atr * self.atr_tp2_mult)

        confidence = 0.9 if tp1 > al else 1.0

        return self._make_short_signal(
            symbol=symbol,
            timestamp=ts,
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            confidence=confidence,
            notes=f"LKZ Short | Asian range {al:.5f}–{ah:.5f} | RSI={rsi:.1f}",
        )
