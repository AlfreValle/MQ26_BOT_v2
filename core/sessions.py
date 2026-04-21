"""
Detector de sesiones de trading — todas las horas en UTC.

Sesiones:
  Tokyo:    00:00 – 09:00 UTC
  London:   07:00 – 16:00 UTC
  New York: 12:00 – 21:00 UTC
  Overlap London/NY: 12:00 – 16:00 UTC

Killzones institucionales (ICT):
  Asia KZ:      00:00 – 04:00 UTC
  London KZ:    07:00 – 10:00 UTC  ← máxima liquidez forex
  NY AM KZ:     12:00 – 15:00 UTC
  NY Lunch:     15:00 – 17:00 UTC  ← evitar (baja liquidez)
  NY PM KZ:     19:00 – 21:00 UTC

NY Cash Open:   13:30 UTC (09:30 ET)
NY Cash Close:  20:00 UTC (16:00 ET)
London Fix Gold: 14:30 UTC (10:30 ET)
"""
from __future__ import annotations

from datetime import time
from enum import Enum, auto
from typing import Optional

import pandas as pd


class Session(Enum):
    TOKYO = auto()
    LONDON = auto()
    NEW_YORK = auto()
    OVERLAP = auto()          # London + NY solapamiento
    DEAD = auto()             # Sin sesión activa


class Killzone(Enum):
    ASIA_KZ = auto()
    LONDON_KZ = auto()        # El más importante para forex
    NY_AM_KZ = auto()
    NY_LUNCH = auto()         # Evitar
    NY_PM_KZ = auto()
    NONE = auto()


# ─── Límites UTC de sesiones ────────────────────────────────────────────────
_SESSION_RANGES: list[tuple[time, time, Session]] = [
    (time(0, 0),  time(9, 0),  Session.TOKYO),
    (time(7, 0),  time(12, 0), Session.LONDON),
    (time(12, 0), time(16, 0), Session.OVERLAP),
    (time(16, 0), time(21, 0), Session.NEW_YORK),
]

_KILLZONE_RANGES: list[tuple[time, time, Killzone]] = [
    (time(0, 0),  time(4, 0),  Killzone.ASIA_KZ),
    (time(7, 0),  time(10, 0), Killzone.LONDON_KZ),
    (time(12, 0), time(13, 30),Killzone.NY_AM_KZ),
    (time(13, 30),time(17, 0), Killzone.NY_LUNCH),
    (time(19, 0), time(21, 0), Killzone.NY_PM_KZ),
]

# Risk multipliers por sesión (para scalping)
SESSION_RISK_MULT: dict[Session, float] = {
    Session.TOKYO:    0.6,
    Session.LONDON:   1.0,
    Session.OVERLAP:  1.0,
    Session.NEW_YORK: 1.0,
    Session.DEAD:     0.0,  # No operar
}


def get_session(dt: pd.Timestamp) -> Session:
    """Retorna la sesión activa para un timestamp UTC."""
    t = dt.tz_convert("UTC").time() if dt.tzinfo else dt.time()
    # La sesión de mayor prioridad si hay solapamiento
    for start, end, session in reversed(_SESSION_RANGES):
        if start <= t < end:
            return session
    return Session.DEAD


def get_killzone(dt: pd.Timestamp) -> Killzone:
    """Retorna la killzone activa para un timestamp UTC."""
    t = dt.tz_convert("UTC").time() if dt.tzinfo else dt.time()
    for start, end, kz in _KILLZONE_RANGES:
        if start <= t < end:
            return kz
    return Killzone.NONE


def is_london_killzone(dt: pd.Timestamp) -> bool:
    return get_killzone(dt) == Killzone.LONDON_KZ


def is_ny_open(dt: pd.Timestamp) -> bool:
    """True si estamos en la apertura de NY Cash (13:30–15:30 UTC)."""
    t = dt.tz_convert("UTC").time() if dt.tzinfo else dt.time()
    return time(13, 30) <= t < time(15, 30)


def is_london_fix(dt: pd.Timestamp) -> bool:
    """True si estamos cerca del London Gold Fix (14:15–14:45 UTC)."""
    t = dt.tz_convert("UTC").time() if dt.tzinfo else dt.time()
    return time(14, 15) <= t < time(14, 45)


def is_asian_session(dt: pd.Timestamp) -> bool:
    return get_session(dt) == Session.TOKYO


def is_london_session(dt: pd.Timestamp) -> bool:
    return get_session(dt) in (Session.LONDON, Session.OVERLAP)


def is_ny_session(dt: pd.Timestamp) -> bool:
    return get_session(dt) in (Session.NEW_YORK, Session.OVERLAP)


def should_avoid_trade(dt: pd.Timestamp) -> bool:
    """True si NO se debe abrir nuevas posiciones (lunch, sin sesión)."""
    kz = get_killzone(dt)
    sess = get_session(dt)
    return kz == Killzone.NY_LUNCH or sess == Session.DEAD


def add_session_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega columnas de sesión a un DataFrame OHLCV con DatetimeTZ index.
    Columnas añadidas:
      session       : nombre de la sesión
      killzone      : nombre de la killzone
      is_london_kz  : bool
      is_ny_open    : bool
      risk_mult     : multiplicador de riesgo
    """
    df = df.copy()
    df["session"]      = df.index.map(get_session)
    df["killzone"]     = df.index.map(get_killzone)
    df["is_london_kz"] = df.index.map(is_london_killzone)
    df["is_ny_open"]   = df.index.map(is_ny_open)
    df["risk_mult"]    = df["session"].map(SESSION_RISK_MULT).fillna(0.0)
    return df


def get_asian_range(df_h1: pd.DataFrame, date: pd.Timestamp) -> Optional[dict]:
    """
    Calcula el rango asiático (00:00–07:00 UTC) para una fecha dada.

    Args:
        df_h1: DataFrame H1 con DatetimeTZ index en UTC
        date: Fecha para calcular el rango

    Returns:
        {"high": float, "low": float, "range_pips_raw": float, "open": float}
        o None si no hay suficientes datos
    """
    day_str = date.strftime("%Y-%m-%d")
    asian_start = pd.Timestamp(f"{day_str} 00:00:00", tz="UTC")
    asian_end   = pd.Timestamp(f"{day_str} 07:00:00", tz="UTC")

    mask = (df_h1.index >= asian_start) & (df_h1.index < asian_end)
    session_bars = df_h1[mask]

    if session_bars.empty or len(session_bars) < 3:
        return None

    return {
        "high":           float(session_bars["high"].max()),
        "low":            float(session_bars["low"].min()),
        "open":           float(session_bars["open"].iloc[0]),
        "close":          float(session_bars["close"].iloc[-1]),
        "range_raw":      float(session_bars["high"].max() - session_bars["low"].min()),
        "n_bars":         len(session_bars),
        "asian_start":    asian_start,
        "asian_end":      asian_end,
    }
