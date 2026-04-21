"""
Análisis de Estructura de Mercado — ICT / Smart Money Concepts.

Detecta:
  - HH / HL / LH / LL  (Higher High, Higher Low, Lower High, Lower Low)
  - Order Blocks (OB)   — última vela contraria antes de un impulso
  - Fair Value Gaps (FVG) — zonas de desequilibrio entre velas
  - Break of Structure (BOS)
  - Change of Character (ChoCH)
  - Swing Highs / Swing Lows
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np
import pandas as pd


# ─── Tipos de datos ─────────────────────────────────────────────────────────

@dataclass
class SwingPoint:
    idx: pd.Timestamp
    price: float
    kind: Literal["high", "low"]
    bar_index: int


@dataclass
class OrderBlock:
    idx: pd.Timestamp
    top: float           # Precio más alto del OB
    bottom: float        # Precio más bajo del OB
    mid: float           # 50% del OB (zona de entrada ideal)
    kind: Literal["bullish", "bearish"]
    impulse_start: float # Precio del inicio del impulso que creó el OB
    valid: bool = True   # Se invalida si el precio cierra fuera del OB


@dataclass
class FairValueGap:
    idx: pd.Timestamp       # Timestamp de la vela central (la que creó el gap)
    top: float              # Límite superior del FVG
    bottom: float           # Límite inferior del FVG
    mid: float              # 50% del FVG
    kind: Literal["bullish", "bearish"]
    filled_pct: float = 0.0  # 0.0 = no llenado, 1.0 = 100% llenado
    valid: bool = True        # Se invalida si se llena al 100%


# ─── Análisis de estructura ─────────────────────────────────────────────────

def find_swing_points(
    df: pd.DataFrame,
    left_bars: int = 3,
    right_bars: int = 3,
) -> list[SwingPoint]:
    """
    Detecta swing highs y swing lows.
    Un swing high: high[i] es el máximo de las N velas a cada lado.
    Un swing low:  low[i] es el mínimo de las N velas a cada lado.
    """
    swings: list[SwingPoint] = []
    n = len(df)
    highs = df["high"].values
    lows = df["low"].values
    idx = df.index

    for i in range(left_bars, n - right_bars):
        window_high = highs[i - left_bars: i + right_bars + 1]
        window_low  = lows[i - left_bars: i + right_bars + 1]

        if highs[i] == window_high.max() and highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            swings.append(SwingPoint(
                idx=idx[i], price=highs[i], kind="high", bar_index=i
            ))
        if lows[i] == window_low.min() and lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            swings.append(SwingPoint(
                idx=idx[i], price=lows[i], kind="low", bar_index=i
            ))

    return swings


def classify_market_structure(swings: list[SwingPoint]) -> str:
    """
    Retorna 'bullish', 'bearish', o 'ranging'.
    Analiza la secuencia de swing highs y lows.
    """
    highs = [s for s in swings if s.kind == "high"]
    lows  = [s for s in swings if s.kind == "low"]

    if len(highs) < 2 or len(lows) < 2:
        return "ranging"

    last_highs = [h.price for h in highs[-3:]]
    last_lows  = [l.price for l in lows[-3:]]

    hh = all(last_highs[i] < last_highs[i+1] for i in range(len(last_highs)-1))
    hl = all(last_lows[i] < last_lows[i+1] for i in range(len(last_lows)-1))
    lh = all(last_highs[i] > last_highs[i+1] for i in range(len(last_highs)-1))
    ll = all(last_lows[i] > last_lows[i+1] for i in range(len(last_lows)-1))

    if hh and hl:
        return "bullish"
    if lh and ll:
        return "bearish"
    return "ranging"


def find_order_blocks(
    df: pd.DataFrame,
    lookback: int = 50,
    min_impulse_pct: float = 0.001,  # 0.1% de movimiento mínimo del impulso
) -> list[OrderBlock]:
    """
    Detecta Order Blocks (OBs).

    OB Alcista: última vela BAJISTA antes de un impulso alcista fuerte.
    OB Bajista: última vela ALCISTA antes de un impulso bajista fuerte.

    El impulso se define como un movimiento > min_impulse_pct en la vela siguiente.
    """
    obs: list[OrderBlock] = []
    n = min(len(df), lookback + 1)
    subset = df.iloc[-n:].copy()

    opens  = subset["open"].values
    closes = subset["close"].values
    highs  = subset["high"].values
    lows   = subset["low"].values
    idx    = subset.index

    for i in range(1, len(subset) - 1):
        # Impulso de la vela siguiente (i+1 relativo a la vela de OB i)
        impulse = (closes[i+1] - opens[i+1]) / opens[i+1]

        # OB Alcista: vela i es bajista, vela i+1 es alcista fuerte
        if closes[i] < opens[i] and impulse > min_impulse_pct:
            ob = OrderBlock(
                idx=idx[i],
                top=max(opens[i], closes[i]),
                bottom=min(opens[i], closes[i]),
                mid=(opens[i] + closes[i]) / 2,
                kind="bullish",
                impulse_start=closes[i+1],
            )
            obs.append(ob)

        # OB Bajista: vela i es alcista, vela i+1 es bajista fuerte
        elif closes[i] > opens[i] and impulse < -min_impulse_pct:
            ob = OrderBlock(
                idx=idx[i],
                top=max(opens[i], closes[i]),
                bottom=min(opens[i], closes[i]),
                mid=(opens[i] + closes[i]) / 2,
                kind="bearish",
                impulse_start=closes[i+1],
            )
            obs.append(ob)

    return obs


def find_fair_value_gaps(
    df: pd.DataFrame,
    lookback: int = 100,
    min_gap_pct: float = 0.0002,  # 0.02% del precio (≈2 pips en EURUSD)
) -> list[FairValueGap]:
    """
    Detecta Fair Value Gaps (FVGs) / Imbalances.

    FVG Alcista: high[i-1] < low[i+1]  → gap entre esas dos velas
    FVG Bajista: low[i-1] > high[i+1]  → gap entre esas dos velas

    La vela central (i) es la que creó el desequilibrio.
    """
    fvgs: list[FairValueGap] = []
    n = min(len(df), lookback + 2)
    subset = df.iloc[-n:].copy()

    highs = subset["high"].values
    lows  = subset["low"].values
    idx   = subset.index

    for i in range(1, len(subset) - 1):
        price_ref = (highs[i] + lows[i]) / 2

        # FVG Alcista
        gap_bottom = highs[i-1]
        gap_top    = lows[i+1]
        if gap_top > gap_bottom:
            gap_size = (gap_top - gap_bottom) / price_ref
            if gap_size >= min_gap_pct:
                fvgs.append(FairValueGap(
                    idx=idx[i],
                    top=gap_top,
                    bottom=gap_bottom,
                    mid=(gap_top + gap_bottom) / 2,
                    kind="bullish",
                ))

        # FVG Bajista
        gap_top_b    = lows[i-1]
        gap_bottom_b = highs[i+1]
        if gap_top_b > gap_bottom_b:
            gap_size = (gap_top_b - gap_bottom_b) / price_ref
            if gap_size >= min_gap_pct:
                fvgs.append(FairValueGap(
                    idx=idx[i],
                    top=gap_top_b,
                    bottom=gap_bottom_b,
                    mid=(gap_top_b + gap_bottom_b) / 2,
                    kind="bearish",
                ))

    return fvgs


def update_fvg_fill(fvg: FairValueGap, current_high: float, current_low: float) -> FairValueGap:
    """
    Actualiza el porcentaje de llenado de un FVG dado el precio actual.
    Un FVG se invalida si el precio atraviesa el 100% de la zona.
    """
    if not fvg.valid:
        return fvg

    fvg_range = fvg.top - fvg.bottom

    if fvg.kind == "bullish":
        # El precio baja hacia el FVG
        penetration = fvg.top - current_low
        fvg.filled_pct = min(1.0, max(0.0, penetration / fvg_range))
        if current_low < fvg.bottom:  # Precio atravesó el 100% del FVG
            fvg.valid = False
    else:
        # El precio sube hacia el FVG bajista
        penetration = current_high - fvg.bottom
        fvg.filled_pct = min(1.0, max(0.0, penetration / fvg_range))
        if current_high > fvg.top:
            fvg.valid = False

    return fvg


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega indicadores técnicos core al DataFrame OHLCV.
    Requiere pandas-ta instalado.

    Indicadores añadidos:
      rsi_14        : RSI de 14 períodos
      atr_14        : ATR de 14 períodos
      sma_20        : SMA de 20 períodos
      sma_50        : SMA de 50 períodos
      sma_150       : SMA de 150 períodos (MOD-23)
      ema_20        : EMA de 20 períodos
      bb_upper      : Bollinger Band superior (20, 2σ)
      bb_mid        : Bollinger Band media
      bb_lower      : Bollinger Band inferior
      bb_width      : Ancho de BB normalizado
      adx           : ADX de 14 períodos
      vol_sma20     : SMA del volumen (20 períodos)
      atr_sma50     : SMA del ATR (50 períodos) — para squeeze
    """
    import pandas_ta as ta  # noqa: F401

    df = df.copy()

    # RSI
    df["rsi_14"] = ta.rsi(df["close"], length=14)

    # ATR
    df["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)

    # Moving Averages
    df["sma_20"]  = ta.sma(df["close"], length=20)
    df["sma_50"]  = ta.sma(df["close"], length=50)
    df["sma_150"] = ta.sma(df["close"], length=150)
    df["ema_8"]   = ta.ema(df["close"], length=8)
    df["ema_20"]  = ta.ema(df["close"], length=20)
    df["ema_21"]  = ta.ema(df["close"], length=21)
    df["ema_50"]  = ta.ema(df["close"], length=50)

    # EMA Ribbon alignment flags
    # Bullish: ema8 > ema21 > ema50 (precios sobre todas las EMAs → uptrend sólido)
    df["ema_ribbon_bull"] = (
        df["ema_8"].notna() & df["ema_21"].notna() & df["ema_50"].notna()
        & (df["ema_8"] > df["ema_21"])
        & (df["ema_21"] > df["ema_50"])
    )
    df["ema_ribbon_bear"] = (
        df["ema_8"].notna() & df["ema_21"].notna() & df["ema_50"].notna()
        & (df["ema_8"] < df["ema_21"])
        & (df["ema_21"] < df["ema_50"])
    )

    # Bollinger Bands
    bb = ta.bbands(df["close"], length=20, std=2)
    if bb is not None:
        df["bb_upper"] = bb.get("BBU_20_2.0")
        df["bb_mid"]   = bb.get("BBM_20_2.0")
        df["bb_lower"] = bb.get("BBL_20_2.0")
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
    else:
        df["bb_upper"] = df["bb_mid"] = df["bb_lower"] = df["bb_width"] = float("nan")

    # ADX con DI+ y DI- (dirección de la tendencia)
    adx = ta.adx(df["high"], df["low"], df["close"], length=14)
    if adx is not None:
        df["adx"]   = adx.get("ADX_14")
        df["di_pos"] = adx.get("DMP_14")   # DI+ (buyers dominan cuando > DI-)
        df["di_neg"] = adx.get("DMN_14")   # DI- (sellers dominan cuando > DI+)
    else:
        df["adx"] = df["di_pos"] = df["di_neg"] = float("nan")

    # Volumen SMA
    df["vol_sma20"] = ta.sma(df["volume"], length=20)

    # ATR SMA para detección de squeeze
    df["atr_sma50"] = ta.sma(df["atr_14"], length=50)

    # Momentum (3 meses ≈ 60 barras en H1)
    df["momentum_60"] = df["close"].pct_change(60)

    # Cuerpo de vela como % del rango
    df["body_pct"] = abs(df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-10)

    # Dirección de vela
    df["is_bullish"] = df["close"] > df["open"]
    df["is_bearish"] = df["close"] < df["open"]

    return df


def detect_engulfing(df: pd.DataFrame, idx: int) -> Optional[Literal["bullish", "bearish"]]:
    """
    Detecta patrón engulfing en la posición idx.
    - Bullish engulfing: vela previa bajista, vela actual alcista y cubre a la previa
    - Bearish engulfing: vela previa alcista, vela actual bajista y cubre a la previa
    """
    if idx < 1:
        return None

    prev = df.iloc[idx - 1]
    curr = df.iloc[idx]

    if (prev["is_bearish"] and curr["is_bullish"]
            and curr["open"] <= prev["close"]
            and curr["close"] >= prev["open"]):
        return "bullish"

    if (prev["is_bullish"] and curr["is_bearish"]
            and curr["open"] >= prev["close"]
            and curr["close"] <= prev["open"]):
        return "bearish"

    return None


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calcula el VWAP intradía.
    Para backtest se calcula por día completo.
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cumulative_vol = df.groupby(df.index.date)["volume"].cumsum()
    cumulative_tp_vol = (typical_price * df["volume"]).groupby(df.index.date).cumsum()
    vwap = cumulative_tp_vol / cumulative_vol
    return vwap


def compute_vwap_bands(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula VWAP + bandas de desviación estándar 1σ y 2σ.
    Necesario para la estrategia VWAP Bounce Institucional (Índices E2).
    """
    df = df.copy()
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"] = compute_vwap(df)

    # Varianza intradía del precio ponderada por volumen
    def _vwap_std(group):
        tp = (group["high"] + group["low"] + group["close"]) / 3
        vol = group["volume"]
        vwap_val = (tp * vol).cumsum() / vol.cumsum()
        variance = ((tp - vwap_val) ** 2 * vol).cumsum() / vol.cumsum()
        return variance ** 0.5

    std_series = df.groupby(df.index.date, group_keys=False).apply(_vwap_std)
    df["vwap_std"] = std_series

    df["vwap_upper1"] = df["vwap"] + df["vwap_std"]
    df["vwap_lower1"] = df["vwap"] - df["vwap_std"]
    df["vwap_upper2"] = df["vwap"] + 2 * df["vwap_std"]
    df["vwap_lower2"] = df["vwap"] - 2 * df["vwap_std"]

    return df
