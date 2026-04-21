"""
ESTRATEGIA 5 — VWAP Bounce Institucional (Índices)

Concepto: El VWAP (Volume Weighted Average Price) es el precio promedio
ponderado del día. Los institucionales usan el VWAP como referencia para
acumular/distribuir. Cuando el precio se desvía 1.5–2 desviaciones estándar,
hay alta probabilidad de reversión al VWAP.

Señales:
  LONG:  Precio toca VWAP − 1.5 SD + RSI oversold + vela alcista de reversión
  SHORT: Precio toca VWAP + 1.5 SD + RSI overbought + vela bajista de reversión

Mejor en: SP500, Dow Jones (alta liquidez, VWAP más respetado)
Timeframe: M5 intraday
Sesión:    NY 14:00–19:30 UTC (10:00–15:30 ET) — evitar primeros 30 min ORB
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class VWAPBounceStrategy(BaseStrategy):
    strategy_id = "S05_VWAPBounce"
    asset_class = "index"
    timeframe_signal  = "M5"
    timeframe_context = "M5"

    # Parámetros — calibrados para M5 de índices (SP500/DOW)
    vwap_sd_entry: float = 1.2     # Entrar en VWAP ± 1.2 SD (más alcanzable)
    vwap_sd_sl:    float = 2.0     # SL en VWAP ± 2.0 SD
    rsi_oversold:  float = 45.0    # RSI < 45 para longs (índices rebotan antes de 38)
    rsi_overbought: float = 55.0   # RSI > 55 para shorts
    min_body_pct:  float = 0.25    # Cuerpo mínimo 25%
    max_signals_per_day: int = 4
    atr_sl_buffer: float = 0.3

    def generate_signals(
        self,
        df_signal: pd.DataFrame,
        df_context: pd.DataFrame,
        symbol: str,
    ) -> list[Signal]:
        if df_signal.empty:
            return []

        signals: list[Signal] = []
        dates = df_signal.index.normalize().unique()

        for date in dates:
            day_sigs = self._process_day(df_signal, symbol, date)
            signals.extend(day_sigs)

        return signals

    def _process_day(
        self,
        df: pd.DataFrame,
        symbol: str,
        date: pd.Timestamp,
    ) -> list[Signal]:
        day_str = date.strftime("%Y-%m-%d")

        # Rango de trading: 14:00–19:30 UTC (evitar open ORB y cierre)
        session_start = pd.Timestamp(f"{day_str} 14:00:00", tz="UTC")
        session_end   = pd.Timestamp(f"{day_str} 19:30:00", tz="UTC")
        ny_open       = pd.Timestamp(f"{day_str} 13:30:00", tz="UTC")

        # VWAP desde el NY open — solo el día actual
        df_vwap = df[(df.index >= ny_open) & (df.index.normalize() == date)].copy()
        if len(df_vwap) < 6:
            return []

        # Calcular VWAP + bandas de desviación estándar
        df_vwap["typical"] = (df_vwap["high"] + df_vwap["low"] + df_vwap["close"]) / 3
        df_vwap["cum_tv"]  = (df_vwap["typical"] * df_vwap["volume"]).cumsum()
        df_vwap["cum_vol"] = df_vwap["volume"].cumsum()
        df_vwap["vwap"]    = df_vwap["cum_tv"] / df_vwap["cum_vol"].replace(0, float("nan"))

        # SD acumulada: varianza media de (precio típico − VWAP)
        dev = df_vwap["typical"] - df_vwap["vwap"]
        df_vwap["vwap_sd"] = np.sqrt((dev ** 2).expanding().mean()).fillna(0)

        # Zonas de entrada y SL
        df_vwap["vwap_lo_entry"] = df_vwap["vwap"] - self.vwap_sd_entry * df_vwap["vwap_sd"]
        df_vwap["vwap_hi_entry"] = df_vwap["vwap"] + self.vwap_sd_entry * df_vwap["vwap_sd"]
        df_vwap["vwap_lo_sl"]    = df_vwap["vwap"] - self.vwap_sd_sl    * df_vwap["vwap_sd"]
        df_vwap["vwap_hi_sl"]    = df_vwap["vwap"] + self.vwap_sd_sl    * df_vwap["vwap_sd"]

        # Zona de trading
        df_trade = df_vwap[
            (df_vwap.index >= session_start) & (df_vwap.index < session_end)
        ]

        if len(df_trade) < 2:
            return []

        signals: list[Signal] = []
        count = 0

        for i in range(1, len(df_trade)):
            if count >= self.max_signals_per_day:
                break

            bar = df_trade.iloc[i]
            ts  = df_trade.index[i]

            atr  = bar.get("atr_14")
            if pd.isna(atr) or atr <= 0:
                continue

            rsi      = bar.get("rsi_14", 50)
            vwap     = bar.get("vwap", float("nan"))
            lo_entry = bar.get("vwap_lo_entry", float("nan"))
            hi_entry = bar.get("vwap_hi_entry", float("nan"))
            lo_sl    = bar.get("vwap_lo_sl", float("nan"))
            hi_sl    = bar.get("vwap_hi_sl", float("nan"))
            body_pct = bar.get("body_pct", 0)

            if any(pd.isna(x) for x in [vwap, lo_entry, hi_entry, lo_sl, hi_sl]):
                continue

            # ── LONG: precio en zona −1.2 SD ──────────────────────────────
            if (bar["low"] <= lo_entry
                    and bar["close"] > lo_entry
                    and rsi < self.rsi_oversold
                    and bar["close"] > bar["open"]  # vela alcista
                    and body_pct >= self.min_body_pct):

                entry = bar["close"]
                sl    = lo_sl - (atr * self.atr_sl_buffer)
                risk  = entry - sl
                # TP basado en R:R — supera el umbral is_valid (>= 1.5)
                tp1   = entry + risk * 1.5   # TP1 en VWAP o más allá
                tp2   = entry + risk * 2.5   # TP2 hacia la banda opuesta

                if risk > 0:
                    sig = self._make_long_signal(
                        symbol=symbol, timestamp=ts,
                        entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                        notes=(
                            f"VWAP Bounce Long | VWAP={vwap:.1f} "
                            f"| -1.2SD={lo_entry:.1f} | RSI={rsi:.1f}"
                        ),
                    )
                    if sig and sig.is_valid:
                        signals.append(sig)
                        count += 1

            # ── SHORT: precio en zona +1.2 SD ─────────────────────────────
            elif (bar["high"] >= hi_entry
                    and bar["close"] < hi_entry
                    and rsi > self.rsi_overbought
                    and bar["close"] < bar["open"]  # vela bajista
                    and body_pct >= self.min_body_pct):

                entry = bar["close"]
                sl    = hi_sl + (atr * self.atr_sl_buffer)
                risk  = sl - entry
                tp1   = entry - risk * 1.5
                tp2   = entry - risk * 2.5

                if risk > 0:
                    sig = self._make_short_signal(
                        symbol=symbol, timestamp=ts,
                        entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                        notes=(
                            f"VWAP Bounce Short | VWAP={vwap:.1f} "
                            f"| +1.2SD={hi_entry:.1f} | RSI={rsi:.1f}"
                        ),
                    )
                    if sig and sig.is_valid:
                        signals.append(sig)
                        count += 1

        return signals
