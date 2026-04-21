"""
ESTRATEGIA 6 — First Hour Momentum (Índices)

Concepto: La primera hora del cash open de NY (13:30–14:30 UTC) establece
el sesgo direccional del día. Si el precio se mueve con momentum claro
(> 0.25% en una dirección) y el volumen confirma, el movimiento continúa
durante las siguientes 1-2 horas. Los institucionales completan sus
posiciones en este período.

Señales:
  LONG:  Primeros 30 min con momentum alcista > 0.25% + cierre sobre VWAP + RSI > 50
  SHORT: Primeros 30 min con momentum bajista > 0.25% + cierre bajo VWAP  + RSI < 50

Mejor en: SP500, NASDAQ, DOW (alta liquidez, momentum limpio en apertura)
Timeframe: M5
Sesión:    NY 14:00–16:00 UTC (entrada post-momentum de apertura)
"""
from __future__ import annotations

import logging

import pandas as pd

from strategies.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class GapAndGoStrategy(BaseStrategy):
    strategy_id = "S06_GapAndGo"
    asset_class = "index"
    timeframe_signal  = "M5"
    timeframe_context = "M5"

    # Parámetros
    momentum_pct: float = 0.0025    # Movimiento mínimo primera hora: 0.25%
    vol_mult: float = 1.2           # Volumen debe ser 120% del promedio
    atr_sl_mult: float = 1.0
    rr_tp1: float = 1.5
    rr_tp2: float = 2.5
    rsi_long_min: float = 50.0
    rsi_short_max: float = 50.0
    max_signals_per_day: int = 1    # Solo 1 señal por día

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

        # 1. Rango de momentum: primeros 30 min del cash open
        ny_open    = pd.Timestamp(f"{day_str} 13:30:00", tz="UTC")
        mom_end    = pd.Timestamp(f"{day_str} 14:00:00", tz="UTC")
        entry_end  = pd.Timestamp(f"{day_str} 16:00:00", tz="UTC")

        df_mom = df[(df.index >= ny_open) & (df.index < mom_end)]
        if len(df_mom) < 3:
            return []

        # 2. Calcular momentum de apertura
        open_price  = float(df_mom["open"].iloc[0])
        close_mom   = float(df_mom["close"].iloc[-1])
        high_mom    = float(df_mom["high"].max())
        low_mom     = float(df_mom["low"].min())

        if open_price <= 0:
            return []

        momentum = (close_mom - open_price) / open_price

        # Determinar sesgo
        if momentum >= self.momentum_pct:
            bias = "long"
        elif momentum <= -self.momentum_pct:
            bias = "short"
        else:
            return []

        # 3. Calcular VWAP desde el open
        df_day = df[(df.index >= ny_open) & (df.index < entry_end)].copy()
        if df_day.empty:
            return []

        df_day["typical"] = (df_day["high"] + df_day["low"] + df_day["close"]) / 3
        df_day["cum_tv"]  = (df_day["typical"] * df_day["volume"]).cumsum()
        df_day["cum_vol"] = df_day["volume"].cumsum()
        df_day["vwap"]    = df_day["cum_tv"] / df_day["cum_vol"].replace(0, float("nan"))

        # 4. Buscar entrada después del momentum (14:00–16:00 UTC)
        df_entry = df_day[df_day.index >= mom_end]
        if df_entry.empty:
            return []

        signals: list[Signal] = []

        for i in range(len(df_entry)):
            bar = df_entry.iloc[i]
            ts  = df_entry.index[i]

            atr = bar.get("atr_14")
            if pd.isna(atr) or atr <= 0:
                continue

            rsi  = bar.get("rsi_14", 50)
            vwap = bar.get("vwap", float("nan"))
            if pd.isna(vwap):
                continue

            vol_sma = bar.get("vol_sma20")
            vol_ok  = pd.isna(vol_sma) or bar["volume"] >= vol_sma * self.vol_mult

            if bias == "long":
                # Confirmación: precio sobre VWAP, RSI > 50, vela alcista
                if (bar["close"] > vwap
                        and rsi >= self.rsi_long_min
                        and bar["close"] > bar["open"]
                        and vol_ok):

                    entry = bar["close"]
                    sl    = low_mom - (atr * self.atr_sl_mult)
                    risk  = entry - sl
                    if risk <= 0:
                        continue

                    tp1 = entry + risk * self.rr_tp1
                    tp2 = entry + risk * self.rr_tp2

                    sig = self._make_long_signal(
                        symbol=symbol, timestamp=ts,
                        entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                        notes=(
                            f"FH Momentum Long | Mom={momentum:+.2%} "
                            f"| VWAP={vwap:.1f} | RSI={rsi:.1f}"
                        ),
                    )
                    if sig and sig.is_valid:
                        signals.append(sig)
                        break

            else:  # bias == "short"
                # Confirmación: precio bajo VWAP, RSI < 50, vela bajista
                if (bar["close"] < vwap
                        and rsi <= self.rsi_short_max
                        and bar["close"] < bar["open"]
                        and vol_ok):

                    entry = bar["close"]
                    sl    = high_mom + (atr * self.atr_sl_mult)
                    risk  = sl - entry
                    if risk <= 0:
                        continue

                    tp1 = entry - risk * self.rr_tp1
                    tp2 = entry - risk * self.rr_tp2

                    sig = self._make_short_signal(
                        symbol=symbol, timestamp=ts,
                        entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                        notes=(
                            f"FH Momentum Short | Mom={momentum:+.2%} "
                            f"| VWAP={vwap:.1f} | RSI={rsi:.1f}"
                        ),
                    )
                    if sig and sig.is_valid:
                        signals.append(sig)
                        break

        return signals
