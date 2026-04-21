"""
ESTRATEGIA 2 — SMC Fair Value Gap Retest

Concepto: Cuando los institucionales mueven el mercado rápidamente dejan FVGs
(zonas de desequilibrio). El precio regresa estadísticamente a llenar el 50%
de esos gaps antes de continuar la tendencia principal (H4/H1).

Señales:
  LONG:  FVG alcista en H1 como soporte + reversión en M15
  SHORT: FVG bajista en H1 como resistencia + reversión en M15

Mejor en: EURUSD, USDJPY, AUDUSD, GBPUSD
Timeframe: H1 (FVG) + M15 (entrada fina)
Sesión:    London + New York (08:00–17:00 UTC)
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from core.market_structure import (
    find_fair_value_gaps,
    find_swing_points,
    classify_market_structure,
    update_fvg_fill,
    FairValueGap,
)
from core.sessions import is_london_session, is_ny_session
from strategies.base import BaseStrategy, Signal, SignalDirection

logger = logging.getLogger(__name__)


class FVGRetestStrategy(BaseStrategy):
    strategy_id = "S02_FVGRetest"
    asset_class = "forex"
    timeframe_signal  = "M15"
    timeframe_context = "H1"

    # Parámetros
    atr_sl_mult: float = 1.2       # SL ajustado: justo bajo/sobre el FVG
    atr_tp1_mult: float = 2.0
    atr_tp2_mult: float = 3.5
    fvg_fill_target: float = 0.50  # Entrada en el 50% del FVG
    max_fvg_age_bars: int = 50     # FVGs de hasta 50 barras H1
    rsi_long_max: float = 55.0     # Relajado: RSI < 55 para long
    rsi_short_min: float = 45.0    # Relajado: RSI > 45 para short
    min_body_pct: float = 0.30     # Cuerpo mínimo de la vela de reversión
    min_trend_confidence: float = 0.6

    def generate_signals(
        self,
        df_signal: pd.DataFrame,   # M15 con indicadores
        df_context: pd.DataFrame,  # H1 con indicadores
        symbol: str,
    ) -> list[Signal]:
        if df_signal.empty or df_context.empty:
            return []

        signals: list[Signal] = []

        # 1. Determinar tendencia en H1 (usamos últimas 40 barras para el contexto reciente)
        df_recent = df_context.iloc[-40:] if len(df_context) > 40 else df_context
        swings = find_swing_points(df_recent, left_bars=2, right_bars=2)
        trend = classify_market_structure(swings)

        # 2. Detectar FVGs en H1 (lookback ampliado)
        fvgs = find_fair_value_gaps(df_context, lookback=100)
        if not fvgs:
            return []

        # FVGs a favor de la tendencia; si ranging, usamos ambos tipos
        if trend == "bullish":
            active_fvgs = [f for f in fvgs if f.kind == "bullish" and f.valid]
        elif trend == "bearish":
            active_fvgs = [f for f in fvgs if f.kind == "bearish" and f.valid]
        else:
            # Mercado lateral: usar todos los FVGs válidos
            active_fvgs = [f for f in fvgs if f.valid]

        if not active_fvgs:
            logger.debug(f"{symbol}: sin FVGs activos")
            return []

        # 3. Verificar si el precio M15 toca algún FVG (barra a barra)
        last_bars = df_signal.iloc[-self.max_fvg_age_bars * 4:]  # M15: 4x más barras que H1
        for bar_idx in range(len(last_bars)):
            bar = last_bars.iloc[bar_idx]
            ts  = last_bars.index[bar_idx]

            # Solo en sesiones activas
            if not (is_london_session(ts) or is_ny_session(ts)):
                continue

            for fvg in active_fvgs:
                # Actualizar estado del FVG
                fvg = update_fvg_fill(fvg, bar["high"], bar["low"])
                if not fvg.valid:
                    continue

                signal = self._check_fvg_entry(
                    fvg, bar, ts, symbol, trend
                )
                if signal and signal.is_valid:
                    signals.append(signal)
                    active_fvgs.remove(fvg)  # Usar cada FVG una sola vez
                    break  # Un signal por barra

        return signals

    def _check_fvg_entry(
        self,
        fvg: FairValueGap,
        bar: pd.Series,
        ts: pd.Timestamp,
        symbol: str,
        trend: str,
    ) -> Optional[Signal]:
        """
        Verifica si la barra actual toca el 50% del FVG y muestra reversión.
        """
        atr = bar.get("atr_14")
        if pd.isna(atr) or atr <= 0:
            return None

        rsi = bar.get("rsi_14", 50)
        if pd.isna(rsi):
            return None

        if fvg.kind == "bullish" and trend == "bullish":
            # El precio toca la zona del FVG (entre bottom y mid)
            price_in_fvg = (bar["low"] <= fvg.mid) and (bar["close"] >= fvg.bottom)
            if not price_in_fvg:
                return None

            # RSI debe estar moderado (no extremo)
            if rsi > self.rsi_long_max:
                return None

            # Vela de reversión alcista
            is_bullish_bar = bar["close"] > bar["open"]
            body_pct = bar.get("body_pct", 0)
            if not is_bullish_bar or body_pct < self.min_body_pct:
                return None

            entry = bar["close"]
            sl    = fvg.bottom - (atr * 0.3)
            tp1   = entry + (atr * self.atr_tp1_mult)
            tp2   = entry + (atr * self.atr_tp2_mult)

            return self._make_long_signal(
                symbol=symbol,
                timestamp=ts,
                entry=entry,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                notes=(
                    f"FVG Long | Zone {fvg.bottom:.5f}–{fvg.top:.5f} | "
                    f"Fill={fvg.filled_pct:.0%} | RSI={rsi:.1f}"
                ),
            )

        elif fvg.kind == "bearish" and trend == "bearish":
            # El precio toca la zona del FVG bajista (entre mid y top)
            price_in_fvg = (bar["high"] >= fvg.mid) and (bar["close"] <= fvg.top)
            if not price_in_fvg:
                return None

            if rsi < self.rsi_short_min:
                return None

            is_bearish_bar = bar["close"] < bar["open"]
            body_pct = bar.get("body_pct", 0)
            if not is_bearish_bar or body_pct < self.min_body_pct:
                return None

            entry = bar["close"]
            sl    = fvg.top + (atr * 0.3)
            tp1   = entry - (atr * self.atr_tp1_mult)
            tp2   = entry - (atr * self.atr_tp2_mult)

            return self._make_short_signal(
                symbol=symbol,
                timestamp=ts,
                entry=entry,
                sl=sl,
                tp1=tp1,
                tp2=tp2,
                notes=(
                    f"FVG Short | Zone {fvg.bottom:.5f}–{fvg.top:.5f} | "
                    f"Fill={fvg.filled_pct:.0%} | RSI={rsi:.1f}"
                ),
            )

        return None
