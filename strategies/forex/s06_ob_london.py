"""
ESTRATEGIA 6 — Order Block London Retest

Concepto: Los market makers crean Order Blocks (OB) institucionales en H1
durante las sesiones previas. Al abrir Londres, el precio frecuentemente
retrocede a testear esos OBs antes de continuar en la dirección del impulso
original. Esta estrategia captura ese retest con gestión de riesgo precisa.

Lógica:
  1. Detectar Order Blocks válidos en H1 (últimas 20 barras pre-London)
  2. Al abrir Londres (07:00–09:00 UTC), esperar que el precio retroceda
     al OB sin invalidarlo (sin cierre fuera del OB)
  3. Entrar en la dirección del impulso original del OB
  4. SL: 0.5x ATR más allá del OB
  5. TP1: 1.5x riesgo | TP2: próximo swing high/low significativo

Filtros:
  - OB debe ser reciente (< 12 barras H1 = 12h)
  - Impulso del OB debe ser > 0.5% del precio
  - Tendencia H1 debe estar alineada con el OB (EMA20)
  - ADX H1 > 15 (mercado con dirección)
  - Body de la vela de entrada > 25%

Mejor en: GBPUSD, EURUSD, AUDUSD, NZDUSD, XAUUSD
Timeframe: M5 (entrada) + H1 (contexto + OBs)
Sesión:    London Open 07:00–09:00 UTC
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from core.market_structure import (
    add_indicators,
    find_order_blocks,
    OrderBlock,
    find_swing_points,
)
from strategies.base import BaseStrategy, Signal, SignalDirection

logger = logging.getLogger(__name__)


class OBLondonStrategy(BaseStrategy):
    strategy_id = "S06_OBLondon"
    asset_class = "forex"
    timeframe_signal  = "M5"
    timeframe_context = "H1"

    # ── Order Block ───────────────────────────────────────────────────────────
    ob_max_age_bars: int       = 20    # Máximo 20 barras H1 de antigüedad (~20h)
    ob_min_impulse_pct: float  = 0.001  # Impulso mínimo del OB: 0.1% (más permisivo)
    ob_touch_tolerance: float  = 0.3   # Hasta 30% del OB puede penetrar sin invalidar

    # ── Filtros de tendencia ─────────────────────────────────────────────────
    ema_period: int   = 20
    adx_min: float    = 15.0
    use_trend: bool   = True

    # ── Entrada y SL ─────────────────────────────────────────────────────────
    sl_atr_mult: float    = 0.5    # SL = 0.5x ATR más allá del OB
    tp1_rr: float         = 1.5    # TP1 = 1.5x riesgo
    tp2_rr: float         = 3.0    # TP2 = 3.0x riesgo
    min_body_pct: float   = 0.25   # Cuerpo mínimo vela entrada (25%)

    # ── Ventana London ────────────────────────────────────────────────────────
    london_start_utc: int = 7    # 07:00 UTC
    london_end_utc: int   = 9    # 09:00 UTC

    def generate_signals(
        self,
        df_signal: pd.DataFrame,
        df_context: pd.DataFrame,
        symbol: str,
    ) -> list[Signal]:
        if df_signal.empty or df_context.empty:
            return []

        signals: list[Signal] = []
        dates = df_signal.index.normalize().unique()

        for date in dates:
            day_sigs = self._process_day(df_signal, df_context, symbol, date)
            signals.extend(day_sigs)

        return signals

    def _process_day(
        self,
        df_m5: pd.DataFrame,
        df_h1: pd.DataFrame,
        symbol: str,
        date: pd.Timestamp,
    ) -> list[Signal]:
        day_str = date.strftime("%Y-%m-%d")

        # ── Contexto H1 pre-London ────────────────────────────────────────────
        h1_pre = df_h1[df_h1.index < pd.Timestamp(f"{day_str} 07:00:00", tz="UTC")]
        if len(h1_pre) < 20:
            return []

        last_h1 = h1_pre.iloc[-1]

        # ── Tendencia EMA20 H1 ────────────────────────────────────────────────
        trend_long  = True
        trend_short = True
        if self.use_trend:
            ema_val = last_h1.get("ema_20", float("nan"))
            if not pd.isna(ema_val):
                trend_long  = last_h1["close"] > ema_val
                trend_short = last_h1["close"] < ema_val

        # ── ADX H1 ───────────────────────────────────────────────────────────
        adx_val = last_h1.get("adx", float("nan"))
        adx_ok  = pd.isna(adx_val) or adx_val >= self.adx_min

        if not adx_ok:
            return []

        # ── ATR H1 para SL ───────────────────────────────────────────────────
        atr_h1 = last_h1.get("atr_14", float("nan"))
        if pd.isna(atr_h1) or atr_h1 <= 0:
            return []

        # ── Detectar Order Blocks en H1 (últimas ob_max_age_bars) ────────────
        # Usar solo las barras H1 recientes para OBs relevantes
        h1_recent = h1_pre.iloc[-self.ob_max_age_bars - 5:]  # Un poco más para contexto
        obs = find_order_blocks(
            h1_recent,
            lookback=self.ob_max_age_bars + 5,
            min_impulse_pct=self.ob_min_impulse_pct,
        )

        if not obs:
            return []

        # Filtrar OBs por antigüedad y dirección de tendencia
        valid_obs: list[OrderBlock] = []
        current_price = last_h1["close"]

        for ob in obs:
            # Validar por tendencia
            if ob.kind == "bullish" and not trend_long:
                continue
            if ob.kind == "bearish" and not trend_short:
                continue

            # OB debe estar cerca del precio actual (no demasiado lejos)
            dist_to_ob = abs(current_price - ob.mid) / current_price
            if dist_to_ob > 0.05:  # Máximo 5% de distancia (ampliado)
                continue

            valid_obs.append(ob)

        if not valid_obs:
            return []

        # ── Ventana London: M5 07:00–09:00 UTC ───────────────────────────────
        lo_start = pd.Timestamp(f"{day_str} 0{self.london_start_utc}:00:00", tz="UTC")
        lo_end   = pd.Timestamp(f"{day_str} 0{self.london_end_utc}:00:00", tz="UTC")
        df_lo    = df_m5[(df_m5.index >= lo_start) & (df_m5.index < lo_end)]

        if df_lo.empty:
            return []

        signals: list[Signal] = []
        used_obs: set[int] = set()  # Evitar usar el mismo OB dos veces

        for i in range(1, len(df_lo)):
            bar      = df_lo.iloc[i]
            ts       = df_lo.index[i]
            atr_m5   = bar.get("atr_14", atr_h1 / 4)  # Fallback a ATR H1/4
            body_pct = bar.get("body_pct", 1.0)

            if pd.isna(atr_m5) or atr_m5 <= 0:
                continue

            for ob_idx, ob in enumerate(valid_obs):
                if ob_idx in used_obs:
                    continue

                sig = self._check_ob_touch(
                    bar, ts, ob, atr_m5, body_pct, symbol, ob_idx
                )

                if sig and sig.is_valid:
                    signals.append(sig)
                    used_obs.add(ob_idx)
                    break  # 1 señal por vela

            if len(signals) >= 2:  # Máximo 2 señales por día
                break

        return signals

    def _check_ob_touch(
        self,
        bar: pd.Series,
        ts: pd.Timestamp,
        ob: OrderBlock,
        atr: float,
        body_pct: float,
        symbol: str,
        ob_idx: int,
    ) -> Optional[Signal]:
        """
        Verifica si la vela actual está tocando el OB y genera señal.
        """
        tolerance = (ob.top - ob.bottom) * self.ob_touch_tolerance

        # ── OB ALCISTA: precio retrocede al OB → entry LONG ──────────────────
        if ob.kind == "bullish":
            # El precio debe tocar la zona del OB (low de la vela dentro del OB)
            ob_touched = (bar["low"] <= ob.top + tolerance) and (bar["low"] >= ob.bottom - tolerance)
            # No debe cerrar DEBAJO del OB (eso lo invalidaría)
            ob_not_broken = bar["close"] >= ob.bottom - tolerance
            # Vela alcista de confirmación (rebote)
            is_bullish = bar["close"] > bar["open"]

            if ob_touched and ob_not_broken and is_bullish and body_pct >= self.min_body_pct:
                entry = bar["close"]
                sl    = ob.bottom - atr * self.sl_atr_mult
                risk  = entry - sl
                if risk <= 0:
                    return None
                tp1 = entry + risk * self.tp1_rr
                tp2 = entry + risk * self.tp2_rr

                return self._make_long_signal(
                    symbol=symbol, timestamp=ts,
                    entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                    notes=(
                        f"OB London Long | OB {ob.bottom:.5f}–{ob.top:.5f} "
                        f"| body={body_pct:.0%}"
                    ),
                )

        # ── OB BAJISTA: precio retrocede al OB → entry SHORT ─────────────────
        elif ob.kind == "bearish":
            ob_touched   = (bar["high"] >= ob.bottom - tolerance) and (bar["high"] <= ob.top + tolerance)
            ob_not_broken = bar["close"] <= ob.top + tolerance
            is_bearish   = bar["close"] < bar["open"]

            if ob_touched and ob_not_broken and is_bearish and body_pct >= self.min_body_pct:
                entry = bar["close"]
                sl    = ob.top + atr * self.sl_atr_mult
                risk  = sl - entry
                if risk <= 0:
                    return None
                tp1 = entry - risk * self.tp1_rr
                tp2 = entry - risk * self.tp2_rr

                return self._make_short_signal(
                    symbol=symbol, timestamp=ts,
                    entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                    notes=(
                        f"OB London Short | OB {ob.bottom:.5f}–{ob.top:.5f} "
                        f"| body={body_pct:.0%}"
                    ),
                )

        return None
