"""
Data Feed — Descarga y cacheo de datos OHLCV multi-timeframe.
Fuente: yfinance (backtesting) → MetaTrader5 (demo/live).
"""
from __future__ import annotations

import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

from config.instruments import Instrument, ALL_INSTRUMENTS
from config.settings import CACHE_DIR, settings

logger = logging.getLogger(__name__)

CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Mapeo de intervalo legible → string de yfinance
YF_INTERVAL_MAP = {
    "M1":  "1m",
    "M5":  "5m",
    "M15": "15m",
    "M30": "30m",
    "H1":  "1h",
    "H4":  "4h",
    "D1":  "1d",
}

# yfinance limita la historia según el intervalo
YF_MAX_PERIOD: dict[str, str] = {
    "1m":  "7d",
    "5m":  "60d",
    "15m": "60d",
    "30m": "60d",
    "1h":  "730d",
    "4h":  "730d",
    "1d":  "5y",
}


def _cache_path(symbol: str, interval: str, period: str) -> Path:
    return CACHE_DIR / f"{symbol}_{interval}_{period}.pkl"


def _load_cache(path: Path, max_age_hours: int = 4) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    if age > timedelta(hours=max_age_hours):
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _save_cache(path: Path, df: pd.DataFrame) -> None:
    with open(path, "wb") as f:
        pickle.dump(df, f)


def fetch_ohlcv(
    symbol: str,
    interval: str = "H1",
    period: str = "auto",
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Descarga OHLCV para un símbolo.

    Args:
        symbol: Símbolo yfinance (e.g. "EURUSD=X") o MT5 (e.g. "EURUSD")
        interval: "M5" | "M15" | "H1" | "H4" | "D1"
        period: "7d" | "60d" | "2y" | "auto" (auto usa el máximo permitido)
        use_cache: Usar caché local para no hacer requests repetidos

    Returns:
        DataFrame con columnas: Open, High, Low, Close, Volume
        Index: DatetimeTZ en UTC
    """
    # Resolver símbolo yfinance
    yf_sym = _resolve_yf_symbol(symbol)
    yf_interval = YF_INTERVAL_MAP.get(interval, interval)

    if period == "auto":
        period = YF_MAX_PERIOD.get(yf_interval, "60d")

    cache_path = _cache_path(yf_sym, yf_interval, period)

    if use_cache:
        cached = _load_cache(cache_path)
        if cached is not None:
            logger.debug(f"Cache hit: {yf_sym} {yf_interval}")
            return cached

    logger.info(f"Descargando {yf_sym} {yf_interval} ({period})...")
    try:
        ticker = yf.Ticker(yf_sym)
        df = ticker.history(period=period, interval=yf_interval, auto_adjust=True)
    except Exception as e:
        logger.error(f"Error descargando {yf_sym}: {e}")
        return pd.DataFrame()

    if df.empty:
        logger.warning(f"Sin datos para {yf_sym} {yf_interval}")
        return pd.DataFrame()

    # Normalizar columnas
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]

    # Asegurar timezone UTC
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    df = df.sort_index()
    df = df.dropna(subset=["open", "high", "low", "close"])

    if use_cache:
        _save_cache(cache_path, df)

    logger.info(f"Datos cargados: {yf_sym} {yf_interval} — {len(df)} barras")
    return df


def fetch_multi_timeframe(
    symbol: str,
    timeframes: list[str] | None = None,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """
    Descarga múltiples timeframes para un símbolo.
    Retorna dict: {"H1": df_h1, "M5": df_m5, ...}
    """
    if timeframes is None:
        timeframes = ["D1", "H1", "M5"]

    result: dict[str, pd.DataFrame] = {}
    for tf in timeframes:
        df = fetch_ohlcv(symbol, interval=tf, use_cache=use_cache)
        if not df.empty:
            result[tf] = df
        else:
            logger.warning(f"No se pudo cargar {symbol} {tf}")
    return result


def fetch_dxy(period: str = "auto", use_cache: bool = True) -> pd.DataFrame:
    """Descarga el DXY (US Dollar Index) — usado como filtro en estrategias de Oro."""
    return fetch_ohlcv("DX-Y.NYB", interval="H1", period=period, use_cache=use_cache)


def _resolve_yf_symbol(symbol: str) -> str:
    """Convierte símbolo MT5 a símbolo yfinance."""
    # Buscar en el mapa de instrumentos
    sym_upper = symbol.upper()
    if sym_upper in ALL_INSTRUMENTS:
        return ALL_INSTRUMENTS[sym_upper].yf_symbol
    # Si ya es formato yfinance (termina en =X o =F), dejarlo
    if "=" in symbol or symbol.endswith(".F"):
        return symbol
    # Intentar agregar =X para forex
    return symbol + "=X"


def resample_to_higher(df: pd.DataFrame, target_interval: str) -> pd.DataFrame:
    """
    Re-muestrea un DataFrame de timeframe bajo a uno alto.
    Útil cuando yfinance no tiene el intervalo exacto.
    target_interval: "4h", "1d", etc. (formato pandas resample)
    """
    resample_map = {
        "4h": "4h",
        "H4": "4h",
        "1d": "1D",
        "D1": "1D",
    }
    rule = resample_map.get(target_interval, target_interval)
    resampled = df.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    return resampled


def get_forex_pairs_data(
    pairs: list[str],
    timeframes: list[str] | None = None,
) -> dict[str, dict[str, pd.DataFrame]]:
    """
    Descarga datos para múltiples pares y timeframes.
    Retorna: {"EURUSD": {"H1": df, "M5": df}, "GBPUSD": {...}, ...}
    """
    if timeframes is None:
        timeframes = ["H1", "M5"]
    result: dict[str, dict[str, pd.DataFrame]] = {}
    for pair in pairs:
        logger.info(f"Cargando {pair}...")
        result[pair] = fetch_multi_timeframe(pair, timeframes)
    return result
