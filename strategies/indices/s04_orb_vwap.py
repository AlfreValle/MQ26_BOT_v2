"""
ESTRATEGIA 4 — Opening Range Breakout + VWAP (Índices)

Concepto: Los primeros 30 minutos del cash open de NY (13:30–14:00 UTC) definen
el rango de apertura (ORB). Cuando el precio rompe ese rango con volumen y VWAP
confirma la dirección, los institucionales ya eligieron el sesgo del día.

Señales:
  LONG:  Rompe ORB High + precio sobre VWAP + volumen > 120% media
  SHORT: Rompe ORB Low  + precio bajo VWAP  + volumen > 120% media

Mejor en: SP500, NASDAQ
Timeframe: M5 (señal), M5 VWAP intraday
Sesión:    NY Cash Open 13:30–16:00 UTC (09:30–12:00 ET)
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from strategies.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class ORBVWAPStrategy(BaseStrategy):
    strategy_id = "S04_ORB_VWAP"
    asset_class = "index"
    timeframe_signal  = "M5"
    timeframe_context = "M5"   # mismo TF — usamos VWAP intraday

    # Parámetros
    orb_minutes: int = 30          # Duración del ORB: 13:30–14:00 UTC
    breakout_buffer_pct: float = 0.0002  # Buffer reducido: 0.02%
    vol_mult: float = 1.1          # Volumen 110% del promedio (más permisivo)
    atr_sl_mult: float = 1.5
    rr_tp1: float = 1.5
    rr_tp2: float = 2.5
    max_signals_per_day: int = 2
    rsi_long_min: float = 40.0     # Relajado: RSI > 40 para long
    rsi_short_max: float = 60.0    # Relajado: RSI < 60 para short

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

        # 1. Extraer el ORB (13:30–14:00 UTC)
        orb_start = pd.Timestamp(f"{day_str} 13:30:00", tz="UTC")
        orb_end   = pd.Timestamp(f"{day_str} 14:00:00", tz="UTC")
        df_orb    = df[(df.index >= orb_start) & (df.index < orb_end)]

        if len(df_orb) < 3:
            return []

        orb_high = float(df_orb["high"].max())
        orb_low  = float(df_orb["low"].min())
        orb_size = orb_high - orb_low

        if orb_size <= 0:
            return []

        # 2. Calcular VWAP intraday (desde el open de NY)
        df_day = df[(df.index >= orb_start) & (df.index.date == date.date())]
        if df_day.empty:
            return []

        df_day = df_day.copy()
        df_day["typical"] = (df_day["high"] + df_day["low"] + df_day["close"]) / 3
        df_day["cum_tv"]  = (df_day["typical"] * df_day["volume"]).cumsum()
        df_day["cum_vol"] = df_day["volume"].cumsum()
        df_day["vwap"]    = df_day["cum_tv"] / df_day["cum_vol"].replace(0, float("nan"))

        # 3. Zona de trading: 14:00–17:00 UTC (no demasiado tarde)
        trade_start = pd.Timestamp(f"{day_str} 14:00:00", tz="UTC")
        trade_end   = pd.Timestamp(f"{day_str} 17:00:00", tz="UTC")
        df_trade = df_day[(df_day.index >= trade_start) & (df_day.index < trade_end)]

        if len(df_trade) < 2:
            return []

        signals: list[Signal] = []
        long_done = False
        short_done = False

        for i in range(1, len(df_trade)):
            bar = df_trade.iloc[i]
            ts  = df_trade.index[i]

            atr = bar.get("atr_14")
            if pd.isna(atr) or atr <= 0:
                continue

            vwap = bar.get("vwap", float("nan"))
            if pd.isna(vwap):
                continue

            rsi = bar.get("rsi_14", 50)
            vol_sma = bar.get("vol_sma20")
            vol_ok  = pd.isna(vol_sma) or bar["volume"] >= vol_sma * self.vol_mult

            # ── LONG: rompe ORB high, precio sobre VWAP ───────────────────
            if not long_done:
                breakout_lvl = orb_high * (1 + self.breakout_buffer_pct)
                if (bar["close"] > breakout_lvl
                        and bar["close"] > vwap
                        and rsi >= self.rsi_long_min
                        and vol_ok):
                    entry = bar["close"]
                    sl    = orb_high - (atr * self.atr_sl_mult)
                    risk  = entry - sl
                    if risk > 0:
                        tp1 = entry + risk * self.rr_tp1
                        tp2 = entry + risk * self.rr_tp2
                        sig = self._make_long_signal(
                            symbol=symbol, timestamp=ts,
                            entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                            notes=(
                                f"ORB Long | ORB {orb_low:.1f}–{orb_high:.1f} "
                                f"| VWAP={vwap:.1f} | RSI={rsi:.1f}"
                            ),
                        )
                        if sig and sig.is_valid:
                            signals.append(sig)
                            long_done = True

            # ── SHORT: rompe ORB low, precio bajo VWAP ────────────────────
            if not short_done:
                breakout_lvl = orb_low * (1 - self.breakout_buffer_pct)
                if (bar["close"] < breakout_lvl
                        and bar["close"] < vwap
                        and rsi <= self.rsi_short_max
                        and vol_ok):
                    entry = bar["close"]
                    sl    = orb_low + (atr * self.atr_sl_mult)
                    risk  = sl - entry
                    if risk > 0:
                        tp1 = entry - risk * self.rr_tp1
                        tp2 = entry - risk * self.rr_tp2
                        sig = self._make_short_signal(
                            symbol=symbol, timestamp=ts,
                            entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                            notes=(
                                f"ORB Short | ORB {orb_low:.1f}–{orb_high:.1f} "
                                f"| VWAP={vwap:.1f} | RSI={rsi:.1f}"
                            ),
                        )
                        if sig and sig.is_valid:
                            signals.append(sig)
                            short_done = True

            if long_done and short_done:
                break

        return signals
