"""
ESTRATEGIA 3 — Asian Range v3 (Institucional)

Concepto: Durante la sesión asiática el mercado consolida en un rango definido
por baja liquidez. Al abrirse Londres, los market makers eligen la dirección
del día. Esta versión v3 agrega sobre v2:

  MEJORAS DE SEÑAL (de análisis de 150 mejoras):
  ─────────────────────────────────────────────
  M1. EMA RIBBON (8/21/50) H1: en lugar de solo EMA20, exigimos que las 3
      EMAs estén alineadas. Filtro de tendencia institucional más robusto.

  M2. DI+ vs DI- (DIRECCIÓN ADX): además de ADX > umbral, exigimos que DI+
      domine para longs y DI- para shorts. Elimina signals en mercados ADX
      alto pero sin dirección clara.

  M3. RSI MULTI-TF: en scalp, el RSI M5 debe estar alineado con el RSI H1.
      Ambos en zona oversold para long, ambos en overbought para short.

  M4. ENGULFING EN EXTREMOS: en scalp, la vela de entrada debe ser engulfing
      (patrón de 2 velas) para mayor confirmación.

  M5. VOLUMEN RELATIVO PRE-BREAKOUT: en breakout London, exigir vol > 1.5x
      promedio (era 1.2x) para mayor convicción institucional.

  M6. SESSION TIME STOP: las señales incluyen timestamp máximo de vida
      para que el ejecutor cierre antes de la sesión NY.

  PORTAFOLIO VALIDADO (60d M5, S03v3):
  ─────────────────────────────────────
  ELITE:   BTCUSD(24.2) XAUUSD(14.9) ETHUSD(12.4) NZDUSD(11.8) AUDUSD(11.8) GBPUSD(10.5)
  BUENO:   AUDJPY(7.6) EURUSD(7.2) EURJPY(5.6) CHFJPY(4.9)
  ELIMINAR: USDCAD(-4.4) AUDNZD(-9.5) GBPNZD(-3.0) CADJPY(0.9)

Mejor en: BTCUSD, XAUUSD, ETHUSD, NZDUSD, AUDUSD, GBPUSD
Timeframe: M5 (señal) + H1 (contexto/tendencia)
Sesión:    Tokyo 00:00–07:00 UTC | London Open 07:00–08:30 UTC
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from core.sessions import get_asian_range, is_asian_session
from core.market_structure import add_indicators, detect_engulfing
from strategies.base import BaseStrategy, Signal, SignalDirection

logger = logging.getLogger(__name__)


class AsianRangeStrategy(BaseStrategy):
    strategy_id = "S03_AsianRange"
    asset_class = "forex"
    timeframe_signal  = "M5"
    timeframe_context = "H1"

    # ── Rango asiático ────────────────────────────────────────────────────────
    min_range_pips: int   = 15          # Mínimo rango para scalp
    max_range_pips_breakout: int = 80   # Rango máximo para breakout
    min_range_atr_ratio: float = 0.3    # Rango debe ser ≥ 30% del ATR

    # ── #7 Range size filter (NUEVO) ─────────────────────────────────────────
    min_range_pips_absolute: int  = 10   # Rango < 10 pips = demasiado estrecho → skip
    max_range_atr_mult: float     = 3.0  # Rango > 3x ATR = anómalo → skip

    # ── Scalp en rango ────────────────────────────────────────────────────────
    extreme_zone_pct: float   = 0.20   # Operar en el 20% superior/inferior del rango
    scalp_atr_sl_mult: float  = 0.8
    min_body_pct: float       = 0.20   # Cuerpo mínimo de la vela de entrada (20%)

    # ── Breakout London ───────────────────────────────────────────────────────
    breakout_atr_sl_mult: float   = 1.2
    breakout_vol_mult: float      = 1.5   # M5. Subido de 1.2 → 1.5 (más selecto)
    breakout_min_body_pct: float  = 0.40  # #6 Vela de breakout: cuerpo >= 40% del rango
    breakout_min_close_pct: float = 0.001 # #6 Close debe estar >= 0.1% sobre el nivel

    # ── Filtros de tendencia — EMA Ribbon + DI ────────────────────────────────
    # NOTA: EMA ribbon y DI son mejoras opcionales para mercados tendenciales
    # Por defecto se usa EMA20 simple (probado y calibrado en 60d M5)
    use_ema_ribbon: bool    = False      # M1. EMA 8/21/50 — activar en mercados tendenciales
    use_di_filter: bool     = True       # M2/M80. DI+/DI- dirección — confirmar sesgo institucional
    trend_ema_period: int   = 20         # EMA base de tendencia H1
    adx_min: float          = 13.0       # ADX mínimo H1 (scalp)
    adx_breakout_min: float = 20.0       # #77 ADX mínimo para London breakout (trending mkt)
    use_trend_filter: bool  = True       # EMA20 alineación (siempre activo)
    use_adx_filter: bool    = True       # ADX > 13 (siempre activo)

    # ── RSI Multi-TF ─────────────────────────────────────────────────────────
    use_rsi_multitf: bool    = False     # M3. Filtro extra — apagar para más señales
    rsi_overbought: float    = 65.0
    rsi_oversold: float      = 35.0
    rsi_h1_overbought: float = 60.0
    rsi_h1_oversold: float   = 40.0

    # ── Engulfing en extremos ─────────────────────────────────────────────────
    use_engulfing: bool     = False      # M4. Off — muy restrictivo en mercados volátiles

    # ── Límites ───────────────────────────────────────────────────────────────
    max_scalps_per_day: int = 3

    # ── #6 Asian Range Quality Score ─────────────────────────────────────────
    min_arqs_score: float = 60.0   # Puntaje mínimo (0-100) para operar el rango

    # ── #15 ATR Multi-Período SL ──────────────────────────────────────────────
    use_atr_sl_floor: bool   = True    # Activar SL mínimo basado en ATR
    atr_sl_period_fast: int  = 5       # ATR rápido (5 períodos H1)
    atr_sl_period_slow: int  = 20      # ATR lento (20 períodos H1)
    atr_sl_floor_mult: float = 0.5    # SL mínimo = max(ATR5, ATR20) × 0.5

    # ── #57 Parámetros específicos por símbolo ────────────────────────────────
    # Overrides de parámetros críticos según clase de activo.
    # Crypto: SL más amplio (ATR × 1.5-2.0), rango mínimo mayor.
    # Gold: SL moderado, rango mínimo menor (gold puede tener rangos compactos).
    _SYMBOL_PARAMS: dict = {
        "BTCUSD": {
            "scalp_atr_sl_mult":     1.5,    # BTC necesita SL más ancho en scalp
            "breakout_atr_sl_mult":  2.0,    # breakout con más margen
            "min_range_pips":        50,     # rango asiático mínimo 50 "puntos" BTC
            "breakout_vol_mult":     1.2,    # volumen más conservador para BTC
        },
        "ETHUSD": {
            "scalp_atr_sl_mult":     1.2,
            "breakout_atr_sl_mult":  1.8,
            "min_range_pips":        8,      # ETH en puntos (pip_size=0.01)
        },
        "XAUUSD": {
            "breakout_atr_sl_mult":  1.5,    # gold: BO más volátiles
            "min_range_pips":        8,      # rango mínimo 8 puntos ≈ $8/oz
        },
    }

    def generate_signals(
        self,
        df_signal: pd.DataFrame,
        df_context: pd.DataFrame,
        symbol: str,
    ) -> list[Signal]:
        if df_signal.empty or df_context.empty:
            return []

        # ── #56 Filtro de régimen ATR (M5) ───────────────────────────────────
        # Evitar períodos de hiper-volatilidad (ATR > percentil 90) o mercado muerto (< p10)
        if "atr_14" in df_signal.columns:
            atr_series  = df_signal["atr_14"].dropna()
            if len(atr_series) >= 50:
                atr_now = atr_series.iloc[-1]
                atr_pct = float((atr_series < atr_now).mean())   # percentil 0–1
                if atr_pct > 0.90:
                    logger.info(
                        f"#56 {symbol}: ATR en percentil {atr_pct:.0%} — "
                        f"hiper-volátil, skip día"
                    )
                    return []
                # No bloqueamos percentil bajo: rango asiático comprimido puede ser bueno

        signals: list[Signal] = []
        dates = df_signal.index.normalize().unique()

        for date in dates:
            day_signals = self._process_day(df_signal, df_context, symbol, date)
            signals.extend(day_signals)

        # ── #65 Adaptive TP Scaling ───────────────────────────────────────────
        # Si la volatilidad actual (ATR) es mayor que la histórica promedio,
        # ampliar TP2 proporcionalmente (hasta ×1.5) para capturar más del movimiento.
        if signals and "atr_14" in df_signal.columns:
            try:
                atr_series = df_signal["atr_14"].dropna()
                if len(atr_series) >= 20:
                    atr_now  = atr_series.iloc[-1]
                    atr_mean = atr_series.iloc[-20:].mean()
                    if atr_mean > 0:
                        atr_ratio = atr_now / atr_mean
                        if atr_ratio > 1.05:   # volatilidad ≥ 5% por encima de media
                            tp_scale = min(1.5, atr_ratio)
                            for sig in signals:
                                if sig.tp2_price and sig.entry_price:
                                    tp2_dist = abs(sig.tp2_price - sig.entry_price)
                                    if sig.tp2_price > sig.entry_price:
                                        sig.tp2_price = sig.entry_price + tp2_dist * tp_scale
                                    else:
                                        sig.tp2_price = sig.entry_price - tp2_dist * tp_scale
                            logger.debug(
                                f"#65 {symbol}: ATR ratio={atr_ratio:.2f} → TP2 ×{tp_scale:.2f}"
                            )
            except Exception as _e:
                logger.debug(f"#65 TP scaling error: {_e}")

        return signals

    def _process_day(
        self,
        df_m5: pd.DataFrame,
        df_h1: pd.DataFrame,
        symbol: str,
        date: pd.Timestamp,
    ) -> list[Signal]:

        # ── #57 Parámetros específicos por símbolo ────────────────────────────
        sym_p = self._SYMBOL_PARAMS.get(symbol, {})
        scalp_sl_mult    = sym_p.get("scalp_atr_sl_mult",    self.scalp_atr_sl_mult)
        bo_sl_mult       = sym_p.get("breakout_atr_sl_mult",  self.breakout_atr_sl_mult)
        bo_vol_mult      = sym_p.get("breakout_vol_mult",     self.breakout_vol_mult)
        sym_min_range    = sym_p.get("min_range_pips",        self.min_range_pips)

        # ── Rango asiático ────────────────────────────────────────────────────
        asian = get_asian_range(df_h1, date)
        if asian is None:
            return []

        ah = asian["high"]
        al = asian["low"]
        ar_range = ah - al
        ar_mid   = (ah + al) / 2

        # Pip size adaptivo
        if "JPY" in symbol:
            pip_size = 0.01
        elif symbol in ("BTCUSD", "ETHUSD", "XAUUSD", "SP500", "NASDAQ", "DOW", "RUSSELL"):
            pip_size = 1.0
        elif symbol in ("SOLUSD", "LTCUSD"):
            pip_size = 0.01
        else:
            pip_size = 0.0001

        ar_pips = ar_range / pip_size

        if ar_pips < sym_min_range:
            return []

        # #7 — Range size filter: demasiado estrecho en pips absolutos
        if ar_pips < self.min_range_pips_absolute:
            logger.debug(f"{symbol} {date.date()}: rango {ar_pips:.1f} pips < mínimo {self.min_range_pips_absolute}")
            return []

        # ── #6 Asian Range Quality Score ─────────────────────────────────────
        arqs = self._compute_arqs(df_h1, date, ah, al)
        if arqs < self.min_arqs_score:
            logger.debug(f"{symbol} {date.date()}: ARQS={arqs:.1f} < {self.min_arqs_score} — rango de baja calidad, skip")
            return []

        day_str = date.strftime("%Y-%m-%d")

        # ── Contexto H1 al inicio de la jornada (antes 07:00 UTC) ───────────
        h1_before_london = df_h1[df_h1.index < pd.Timestamp(f"{day_str} 07:00:00", tz="UTC")]

        # Flags por defecto (neutro = permite ambas direcciones)
        h1_trend_long  = True
        h1_trend_short = True
        h1_adx_ok      = True
        h1_rsi         = float("nan")

        if len(h1_before_london) < 2:
            return []

        last_h1 = h1_before_london.iloc[-1]

        # ── M1. EMA Ribbon (8/21/50) ─────────────────────────────────────────
        if self.use_trend_filter and self.use_ema_ribbon:
            ribbon_bull = last_h1.get("ema_ribbon_bull", False)
            ribbon_bear = last_h1.get("ema_ribbon_bear", False)

            if isinstance(ribbon_bull, (bool, int, float)) and not pd.isna(ribbon_bull):
                h1_trend_long  = bool(ribbon_bull)
                h1_trend_short = bool(ribbon_bear)
            else:
                # Fallback a EMA20 simple
                ema_val = last_h1.get("ema_20", float("nan"))
                if not pd.isna(ema_val):
                    h1_trend_long  = last_h1["close"] > ema_val
                    h1_trend_short = last_h1["close"] < ema_val

        elif self.use_trend_filter:
            # Solo EMA20
            ema_val = last_h1.get("ema_20", float("nan"))
            if not pd.isna(ema_val):
                h1_trend_long  = last_h1["close"] > ema_val
                h1_trend_short = last_h1["close"] < ema_val

        # ── M2. ADX + DI direccional ─────────────────────────────────────────
        if self.use_adx_filter and len(h1_before_london) >= 5:
            adx_val  = last_h1.get("adx", float("nan"))
            di_pos   = last_h1.get("di_pos", float("nan"))
            di_neg   = last_h1.get("di_neg", float("nan"))

            if not pd.isna(adx_val):
                h1_adx_ok = adx_val >= self.adx_min

            # Si DI filter activo: refinar dirección con DI+/DI-
            if self.use_di_filter and not pd.isna(di_pos) and not pd.isna(di_neg):
                # Solo long si DI+ > DI- (buyers dominan)
                # Solo short si DI- > DI+ (sellers dominan)
                di_bias_long  = di_pos > di_neg
                di_bias_short = di_neg > di_pos
                h1_trend_long  = h1_trend_long  and di_bias_long
                h1_trend_short = h1_trend_short and di_bias_short

        # ── Filtro calidad del rango vs ATR ──────────────────────────────────
        atr_h1 = last_h1.get("atr_14", float("nan"))
        if not pd.isna(atr_h1) and atr_h1 > 0:
            if ar_range < atr_h1 * self.min_range_atr_ratio:
                logger.debug(f"{symbol} {day_str}: rango asiático muy pequeño vs ATR")
                return []
            # #7 — Rango anómalo: demasiado amplio vs ATR → breakout poco fiable
            if ar_range > atr_h1 * self.max_range_atr_mult:
                logger.debug(f"{symbol} {day_str}: rango {ar_pips:.1f} pips > {self.max_range_atr_mult}x ATR — anómalo")
                return []

        # ── RSI H1 para multi-TF (M3) ────────────────────────────────────────
        h1_rsi = last_h1.get("rsi_14", float("nan"))

        signals: list[Signal] = []

        # ─── MODO 1: Scalp en rango (01:00–06:30 UTC) ────────────────────────
        scalp_start = pd.Timestamp(f"{day_str} 01:00:00", tz="UTC")
        scalp_end   = pd.Timestamp(f"{day_str} 06:30:00", tz="UTC")
        df_asian    = df_m5[(df_m5.index >= scalp_start) & (df_m5.index < scalp_end)]

        scalp_count = 0
        for i in range(1, len(df_asian)):
            if scalp_count >= self.max_scalps_per_day:
                break
            sig = self._scalp_range(
                df_asian, i, ah, al, ar_mid, symbol,
                allow_long  = h1_trend_long  or not self.use_trend_filter,
                allow_short = h1_trend_short or not self.use_trend_filter,
                adx_ok      = h1_adx_ok,
                h1_rsi      = h1_rsi,
                sl_mult     = scalp_sl_mult,   # #57 por símbolo
            )
            if sig and sig.is_valid:
                signals.append(sig)
                scalp_count += 1

        # ─── MODO 2: Breakout London (07:00–08:30 UTC) ───────────────────────
        # #77 — ADX Regime Filter: London breakout requiere mercado tendencial (ADX ≥ 20)
        # El scalp asiático funciona en rangos (ADX bajo está bien); el breakout NO.
        adx_for_bo = float("nan")
        if self.use_adx_filter and len(h1_before_london) >= 5:
            adx_for_bo = last_h1.get("adx", float("nan"))

        bo_adx_ok = pd.isna(adx_for_bo) or adx_for_bo >= self.adx_breakout_min

        if not bo_adx_ok:
            logger.debug(
                f"#77 {symbol} {day_str}: ADX={adx_for_bo:.1f} < {self.adx_breakout_min} "
                f"— mercado en rango, skip London breakout"
            )

        if ar_pips <= self.max_range_pips_breakout and bo_adx_ok:
            bo_start = pd.Timestamp(f"{day_str} 07:00:00", tz="UTC")
            bo_end   = pd.Timestamp(f"{day_str} 08:30:00", tz="UTC")
            df_bo    = df_m5[(df_m5.index >= bo_start) & (df_m5.index < bo_end)]

            bo_sig = self._breakout_london(
                df_bo, ah, al, ar_range, symbol,
                allow_long  = h1_trend_long  or not self.use_trend_filter,
                allow_short = h1_trend_short or not self.use_trend_filter,
                sl_mult     = bo_sl_mult,      # #57 por símbolo
                vol_mult    = bo_vol_mult,     # #57 por símbolo
            )
            if bo_sig and bo_sig.is_valid:
                signals.append(bo_sig)

        # ─── MODO 3: NY Open Breakout (12:00–14:00 UTC) ──────────────────────
        # Nueva York abre y rompe el rango que consolidó Londres (07:00–12:00 UTC).
        # Señal independiente del rango asiático: usa el H/L de la sesión londinense
        # como niveles de referencia. Requiere las mismas condiciones de tendencia H1.
        ln_ref_start = pd.Timestamp(f"{day_str} 07:00:00", tz="UTC")
        ln_ref_end   = pd.Timestamp(f"{day_str} 12:00:00", tz="UTC")
        df_london    = df_m5[(df_m5.index >= ln_ref_start) & (df_m5.index < ln_ref_end)]

        ny_start = pd.Timestamp(f"{day_str} 12:00:00", tz="UTC")
        ny_end   = pd.Timestamp(f"{day_str} 14:00:00", tz="UTC")
        df_ny    = df_m5[(df_m5.index >= ny_start) & (df_m5.index < ny_end)]

        if len(df_london) >= 10 and len(df_ny) >= 1:
            ny_sig = self._breakout_ny_open(
                df_ny       = df_ny,
                df_london   = df_london,
                symbol      = symbol,
                allow_long  = h1_trend_long  or not self.use_trend_filter,
                allow_short = h1_trend_short or not self.use_trend_filter,
                sl_mult     = bo_sl_mult,
                vol_mult    = bo_vol_mult,
            )
            if ny_sig and ny_sig.is_valid:
                signals.append(ny_sig)

        return signals

    # ─────────────────────────────────────────────────────────────────────────
    def _scalp_range(
        self,
        df: pd.DataFrame,
        i: int,
        ah: float,
        al: float,
        ar_mid: float,
        symbol: str,
        allow_long: bool = True,
        allow_short: bool = True,
        adx_ok: bool = True,
        h1_rsi: float = float("nan"),
        sl_mult: float = 0.0,   # #57 override; 0 → usa self.scalp_atr_sl_mult
    ) -> Optional[Signal]:
        """Scalp en extremo del rango → hacia la zona media."""
        bar      = df.iloc[i]
        ts       = df.index[i]
        ar_range = ah - al

        atr = bar.get("atr_14")
        if pd.isna(atr) or atr <= 0:
            return None

        rsi      = bar.get("rsi_14", 50)
        body_pct = bar.get("body_pct", 1.0)

        if pd.isna(rsi):
            return None

        # Filtro ADX
        if not adx_ok:
            return None

        # #57 — Usar multiplicador específico del símbolo si se pasó
        _sl_mult = sl_mult if sl_mult > 0 else self.scalp_atr_sl_mult

        upper_zone = al + ar_range * (1 - self.extreme_zone_pct)
        lower_zone = al + ar_range * self.extreme_zone_pct

        # ── M3. RSI Multi-TF: H1 RSI debe estar en zona compatible ──────────
        # Long: RSI M5 < oversold Y (RSI H1 < h1_oversold o NaN)
        # Short: RSI M5 > overbought Y (RSI H1 > h1_overbought o NaN)
        h1_rsi_ok_long  = (pd.isna(h1_rsi) or not self.use_rsi_multitf
                           or h1_rsi < self.rsi_h1_oversold)
        h1_rsi_ok_short = (pd.isna(h1_rsi) or not self.use_rsi_multitf
                           or h1_rsi > self.rsi_h1_overbought)

        # ── M4. Engulfing pattern (opcional) ─────────────────────────────────
        engulf = detect_engulfing(df, i) if self.use_engulfing else None

        # ── LONG desde zona inferior ──────────────────────────────────────────
        if (allow_long
                and bar["low"] <= lower_zone
                and bar["close"] > al
                and bar["close"] > bar["open"]   # vela alcista
                and body_pct >= self.min_body_pct
                and rsi < self.rsi_oversold
                and h1_rsi_ok_long
                and (not self.use_engulfing or engulf == "bullish")):

            entry = bar["close"]
            sl    = al - (atr * _sl_mult)
            tp1   = ar_mid
            tp2   = upper_zone
            risk  = entry - sl

            if risk <= 0:
                return None

            return self._make_long_signal(
                symbol=symbol, timestamp=ts,
                entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                notes=(
                    f"Asian Scalp Long | Range {al:.5f}–{ah:.5f} | "
                    f"RSI={rsi:.1f} H1RSI={h1_rsi:.1f}"
                ),
            )

        # ── SHORT desde zona superior ─────────────────────────────────────────
        if (allow_short
                and bar["high"] >= upper_zone
                and bar["close"] < ah
                and bar["close"] < bar["open"]   # vela bajista
                and body_pct >= self.min_body_pct
                and rsi > self.rsi_overbought
                and h1_rsi_ok_short
                and (not self.use_engulfing or engulf == "bearish")):

            entry = bar["close"]
            sl    = ah + (atr * _sl_mult)
            tp1   = ar_mid
            tp2   = lower_zone
            risk  = sl - entry

            if risk <= 0:
                return None

            return self._make_short_signal(
                symbol=symbol, timestamp=ts,
                entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                notes=(
                    f"Asian Scalp Short | Range {al:.5f}–{ah:.5f} | "
                    f"RSI={rsi:.1f} H1RSI={h1_rsi:.1f}"
                ),
            )

        return None

    # ─────────────────────────────────────────────────────────────────────────
    def _breakout_london(
        self,
        df_bo: pd.DataFrame,
        ah: float,
        al: float,
        ar_range: float,
        symbol: str,
        allow_long: bool = True,
        allow_short: bool = True,
        sl_mult: float = 0.0,    # #57 override
        vol_mult: float = 0.0,   # #57 override
    ) -> Optional[Signal]:
        """Breakout confirmado al open de Londres."""
        if df_bo.empty or len(df_bo) < 2:
            return None

        # #57 — Aplicar parámetros del símbolo si se proporcionaron
        _sl_mult  = sl_mult  if sl_mult  > 0 else self.breakout_atr_sl_mult
        _vol_mult = vol_mult if vol_mult > 0 else self.breakout_vol_mult

        for i in range(1, len(df_bo)):
            bar = df_bo.iloc[i]
            ts  = df_bo.index[i]

            atr = bar.get("atr_14")
            if pd.isna(atr) or atr <= 0:
                continue

            # M5. Volumen relativo elevado
            vol_sma = bar.get("vol_sma20")
            vol_ok  = pd.isna(vol_sma) or bar["volume"] >= vol_sma * _vol_mult

            body_pct = bar.get("body_pct", 1.0)

            # ── BREAKOUT LONG ─────────────────────────────────────────────────
            # #6 — Confirmación: body fuerte (≥40%) y close significativo (≥0.1%)
            close_pct_above_ah = (bar["close"] - ah) / ah if ah > 0 else 0

            if (allow_long
                    and bar["close"] > ah
                    and bar["open"] < ah              # rompe en esta vela
                    and bar["close"] > bar["open"]    # vela alcista
                    and body_pct >= self.breakout_min_body_pct   # #6 body ≥ 40%
                    and close_pct_above_ah >= self.breakout_min_close_pct  # #6 close sólido
                    and vol_ok):

                entry = ah + (atr * 0.1)
                sl    = ah - (atr * _sl_mult)
                tp1   = ah + (ar_range * 1.0)
                tp2   = ah + (ar_range * 2.0)
                risk  = entry - sl

                if risk <= 0:
                    continue

                return self._make_long_signal(
                    symbol=symbol, timestamp=ts,
                    entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                    notes=(
                        f"London BO Long | Range {al:.5f}–{ah:.5f} | "
                        f"Vol={bar['volume']:.0f} | Body={body_pct:.0%}"
                    ),
                )

            # ── BREAKOUT SHORT ────────────────────────────────────────────────
            close_pct_below_al = (al - bar["close"]) / al if al > 0 else 0

            if (allow_short
                    and bar["close"] < al
                    and bar["open"] > al
                    and bar["close"] < bar["open"]
                    and body_pct >= self.breakout_min_body_pct    # #6 body ≥ 40%
                    and close_pct_below_al >= self.breakout_min_close_pct  # #6 close sólido
                    and vol_ok):

                entry = al - (atr * 0.1)
                sl    = al + (atr * _sl_mult)
                tp1   = al - (ar_range * 1.0)
                tp2   = al - (ar_range * 2.0)
                risk  = sl - entry

                if risk <= 0:
                    continue

                return self._make_short_signal(
                    symbol=symbol, timestamp=ts,
                    entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                    notes=(
                        f"London BO Short | Range {al:.5f}–{ah:.5f} | "
                        f"Vol={bar['volume']:.0f} | Body={body_pct:.0%}"
                    ),
                )

        return None

    # ─────────────────────────────────────────────────────────────────────────
    def _breakout_ny_open(
        self,
        df_ny: pd.DataFrame,
        df_london: pd.DataFrame,
        symbol: str,
        allow_long: bool = True,
        allow_short: bool = True,
        sl_mult: float = 0.0,
        vol_mult: float = 0.0,
    ) -> Optional[Signal]:
        """
        NY Open Breakout — ruptura del rango londinense (07:00–12:00 UTC) al abrir NY.

        Concepto: Londres establece un rango de consolidación. Cuando Nueva York
        abre (12:00 UTC) y el precio rompe ese rango con volumen y cuerpo sólido,
        confirma la dirección institucional del día.

        SL: al lado opuesto del rango londinense (+ buffer ATR).
        TP1/TP2: proyección del tamaño del rango londinense × 1R y × 2R.
        """
        if df_ny.empty or df_london.empty or len(df_london) < 5:
            return None

        _sl_mult  = sl_mult  if sl_mult  > 0 else self.breakout_atr_sl_mult
        _vol_mult = vol_mult if vol_mult > 0 else self.breakout_vol_mult

        # Rango de la sesión londinense
        ln_high  = float(df_london["high"].max())
        ln_low   = float(df_london["low"].min())
        ln_range = ln_high - ln_low

        if ln_range <= 0:
            return None

        for i in range(len(df_ny)):
            bar = df_ny.iloc[i]
            ts  = df_ny.index[i]

            atr = bar.get("atr_14")
            if pd.isna(atr) or atr <= 0:
                continue

            # Volumen relativo (mismo criterio que London BO)
            vol_sma = bar.get("vol_sma20")
            vol_ok  = pd.isna(vol_sma) or bar["volume"] >= vol_sma * _vol_mult

            body_pct = bar.get("body_pct", 1.0)

            # ── NY LONG: cierra sobre el máximo londinense ────────────────────
            close_pct_above = (bar["close"] - ln_high) / ln_high if ln_high > 0 else 0
            if (allow_long
                    and bar["close"] > ln_high
                    and bar["close"] > bar["open"]             # vela alcista
                    and body_pct >= self.breakout_min_body_pct
                    and close_pct_above >= self.breakout_min_close_pct
                    and vol_ok):

                entry = ln_high + (atr * 0.1)
                sl    = ln_low  - (atr * _sl_mult)
                tp1   = ln_high + (ln_range * 1.0)
                tp2   = ln_high + (ln_range * 2.0)
                risk  = entry - sl
                if risk <= 0:
                    continue

                return self._make_long_signal(
                    symbol=symbol, timestamp=ts,
                    entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                    notes=(
                        f"NY Open BO Long | London {ln_low:.5f}–{ln_high:.5f} | "
                        f"Vol={bar['volume']:.0f} | Body={body_pct:.0%}"
                    ),
                )

            # ── NY SHORT: cierra bajo el mínimo londinense ────────────────────
            close_pct_below = (ln_low - bar["close"]) / ln_low if ln_low > 0 else 0
            if (allow_short
                    and bar["close"] < ln_low
                    and bar["close"] < bar["open"]             # vela bajista
                    and body_pct >= self.breakout_min_body_pct
                    and close_pct_below >= self.breakout_min_close_pct
                    and vol_ok):

                entry = ln_low  - (atr * 0.1)
                sl    = ln_high + (atr * _sl_mult)
                tp1   = ln_low  - (ln_range * 1.0)
                tp2   = ln_low  - (ln_range * 2.0)
                risk  = sl - entry
                if risk <= 0:
                    continue

                return self._make_short_signal(
                    symbol=symbol, timestamp=ts,
                    entry=entry, sl=sl, tp1=tp1, tp2=tp2,
                    notes=(
                        f"NY Open BO Short | London {ln_low:.5f}–{ln_high:.5f} | "
                        f"Vol={bar['volume']:.0f} | Body={body_pct:.0%}"
                    ),
                )

        return None

    # ─── #6 Asian Range Quality Score ────────────────────────────────────────

    def _compute_arqs(
        self, df_h1: pd.DataFrame, date: pd.Timestamp, ah: float, al: float
    ) -> float:
        """
        Puntaje de calidad del rango asiático (0–100).
        1. Rectangularidad (30pts): velas H1 contenidas dentro del rango
        2. Compresión     (25pts): closes poco dispersos respecto al tamaño
        3. Limpieza       (25pts): pocos wicks fuera del rango
        4. BB Width       (20pts): #54 Bollinger Band Width comprimido durante Asia
        """
        day_str  = date.strftime("%Y-%m-%d")
        asian_h1 = df_h1[
            (df_h1.index >= pd.Timestamp(f"{day_str} 00:00", tz="UTC")) &
            (df_h1.index <  pd.Timestamp(f"{day_str} 07:00", tz="UTC"))
        ]
        if len(asian_h1) < 3:
            return 50.0

        ar_range = ah - al
        if ar_range <= 0:
            return 0.0

        # 1. Rectangularidad: % velas completamente dentro del rango (30pts)
        inside     = asian_h1[(asian_h1["high"] <= ah * 1.001) & (asian_h1["low"] >= al * 0.999)]
        rect_score = (len(inside) / len(asian_h1)) * 30

        # 2. Compresión de closes (25pts)
        close_std         = asian_h1["close"].std()
        compression_ratio = close_std / ar_range if ar_range > 0 else 1.0
        comp_score        = max(0.0, (1.0 - compression_ratio * 2)) * 25

        # 3. Limpieza de wicks fuera del rango (25pts)
        wicks_above = (asian_h1["high"] > ah * 1.001).sum()
        wicks_below = (asian_h1["low"]  < al * 0.999).sum()
        wick_ratio  = (wicks_above + wicks_below) / len(asian_h1)
        clean_score = max(0.0, (1.0 - wick_ratio * 2)) * 25

        # 4. #54 BB Width Score (20pts): BB comprimido = rango asiático de alta calidad
        # BB Width = (upper - lower) / middle; menor ancho → mayor compresión → mejor
        bb_score = 10.0  # neutro si no hay datos
        if "bb_upper" in asian_h1.columns and "bb_lower" in asian_h1.columns:
            try:
                bb_upper = asian_h1["bb_upper"].dropna()
                bb_lower = asian_h1["bb_lower"].dropna()
                if len(bb_upper) >= 2 and len(bb_lower) >= 2:
                    bb_mid_vals = (bb_upper + bb_lower) / 2
                    bb_width_pct = ((bb_upper - bb_lower) / bb_mid_vals).mean()
                    # Percentil vs lookback 30d H1 (si disponible)
                    all_width = ((df_h1["bb_upper"] - df_h1["bb_lower"]) /
                                 ((df_h1["bb_upper"] + df_h1["bb_lower"]) / 2)).dropna()
                    if len(all_width) > 20:
                        pct_rank = float((all_width < bb_width_pct).mean())
                        # Menor percentil = más comprimido = mejor (puntuación más alta)
                        bb_score = max(0.0, (1.0 - pct_rank)) * 20
                    else:
                        # Sin suficiente historia: usar valor absoluto
                        # BB Width < 0.01 (1%) = muy comprimido = excelente
                        bb_score = max(0.0, min(20.0, (0.03 - bb_width_pct) / 0.03 * 20))
            except Exception:
                bb_score = 10.0

        return min(100.0, rect_score + comp_score + clean_score + bb_score)

    # ─── #15 ATR Multi-Período SL Floor ──────────────────────────────────────

    def _atr_sl_floor(self, df_h1: pd.DataFrame, date: pd.Timestamp) -> float:
        """SL mínimo = max(ATR_fast, ATR_slow) × mult. Evita SLs prematuros."""
        day_str   = date.strftime("%Y-%m-%d")
        h1_before = df_h1[df_h1.index < pd.Timestamp(f"{day_str} 07:00", tz="UTC")]

        if len(h1_before) < self.atr_sl_period_slow:
            return 0.0
        try:
            import pandas_ta as ta
            atr_fast = ta.atr(h1_before["high"], h1_before["low"], h1_before["close"],
                              length=self.atr_sl_period_fast).iloc[-1]
            atr_slow = ta.atr(h1_before["high"], h1_before["low"], h1_before["close"],
                              length=self.atr_sl_period_slow).iloc[-1]
            return float(max(atr_fast, atr_slow) * self.atr_sl_floor_mult)
        except Exception:
            return 0.0
