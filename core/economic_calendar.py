"""
Filtro de Calendario Económico (M91)

Pausa el trading 30 min antes y 15 min después de eventos de alto impacto.
Fuente de datos: ForexFactory JSON feed (gratuito, sin clave API).

Eventos cubiertos:
  - NFP      (Non-Farm Payrolls)      — 1er viernes de mes, 12:30 UTC
  - CPI USA  (Consumer Price Index)   — ~10-15 de mes, 12:30 UTC
  - Fed Rate Decision                  — ~8 veces/año, 18:00 UTC
  - FOMC Minutes                       — 18:00 UTC
  - ECB Rate Decision                  — ~8 veces/año, 12:15 UTC
  - BOE Rate Decision                  — ~8 veces/año, 12:00 UTC
  - GDP USA (Advance)                  — trimestral, 12:30 UTC
  - Core PCE                           — mensual, 12:30 UTC

Uso:
    from core.economic_calendar import is_news_blackout, get_next_events

    if is_news_blackout():
        logger.warning("Blackout por evento económico — sin nuevas entradas")
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# ─── Configuración ────────────────────────────────────────────────────────────
PAUSE_BEFORE_MIN = 30   # minutos antes del evento
PAUSE_AFTER_MIN  = 30   # #66 — ampliado a 30min post-evento (antes: 15min)
CACHE_FILE       = Path(__file__).resolve().parent.parent / "data" / "cache" / "econ_calendar.json"
CACHE_TTL_HOURS  = 6    # refrescar cada 6h

# Palabras clave de eventos de alto impacto (en inglés, ForexFactory)
HIGH_IMPACT_KEYWORDS = [
    "Non-Farm", "NFP",
    "CPI", "Consumer Price Index",
    "Fed Interest Rate", "FOMC", "Federal Open Market",
    "ECB Interest Rate", "ECB Monetary",
    "BOE Interest Rate", "Bank of England",
    "GDP", "Gross Domestic Product",
    "Core PCE", "PCE Price",
    "Unemployment Rate",
    "Retail Sales",
    "ISM Manufacturing",
    "PPI",
]

# ─── Fallback: calendario hardcoded 2025-2026 ────────────────────────────────
# Si la API no está disponible, usamos fechas conocidas (UTC)
KNOWN_EVENTS_UTC: list[dict] = [
    # NFP 2025
    {"name": "NFP",  "time": "2025-05-02 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP",  "time": "2025-06-06 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP",  "time": "2025-07-04 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP",  "time": "2025-08-01 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP",  "time": "2025-09-05 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP",  "time": "2025-10-03 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP",  "time": "2025-11-07 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP",  "time": "2025-12-05 12:30", "impact": "high", "currencies": ["USD"]},
    # NFP 2026
    {"name": "NFP",  "time": "2026-01-09 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP",  "time": "2026-02-06 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP",  "time": "2026-03-06 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP",  "time": "2026-04-03 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP",  "time": "2026-05-01 12:30", "impact": "high", "currencies": ["USD"]},
    # Fed Rate Decisions 2025-2026 (aproximados)
    {"name": "Fed Rate Decision", "time": "2025-05-07 18:00", "impact": "high", "currencies": ["USD"]},
    {"name": "Fed Rate Decision", "time": "2025-06-18 18:00", "impact": "high", "currencies": ["USD"]},
    {"name": "Fed Rate Decision", "time": "2025-07-30 18:00", "impact": "high", "currencies": ["USD"]},
    {"name": "Fed Rate Decision", "time": "2025-09-17 18:00", "impact": "high", "currencies": ["USD"]},
    {"name": "Fed Rate Decision", "time": "2025-10-29 18:00", "impact": "high", "currencies": ["USD"]},
    {"name": "Fed Rate Decision", "time": "2025-12-17 18:00", "impact": "high", "currencies": ["USD"]},
    {"name": "Fed Rate Decision", "time": "2026-01-28 19:00", "impact": "high", "currencies": ["USD"]},
    {"name": "Fed Rate Decision", "time": "2026-03-18 18:00", "impact": "high", "currencies": ["USD"]},
    # CPI USA (aproximados — 10-15 de cada mes)
    {"name": "CPI",  "time": "2025-05-13 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",  "time": "2025-06-11 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",  "time": "2025-07-15 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",  "time": "2025-08-12 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",  "time": "2025-09-10 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",  "time": "2025-10-15 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",  "time": "2025-11-12 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",  "time": "2025-12-10 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",  "time": "2026-01-14 13:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",  "time": "2026-02-11 13:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",  "time": "2026-03-11 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",  "time": "2026-04-10 12:30", "impact": "high", "currencies": ["USD"]},
    # ECB Rate Decisions
    {"name": "ECB Rate", "time": "2025-06-05 12:15", "impact": "high", "currencies": ["EUR"]},
    {"name": "ECB Rate", "time": "2025-07-24 12:15", "impact": "high", "currencies": ["EUR"]},
    {"name": "ECB Rate", "time": "2025-09-11 12:15", "impact": "high", "currencies": ["EUR"]},
    {"name": "ECB Rate", "time": "2025-10-30 12:15", "impact": "high", "currencies": ["EUR"]},
    {"name": "ECB Rate", "time": "2025-12-18 13:15", "impact": "high", "currencies": ["EUR"]},
    {"name": "ECB Rate", "time": "2026-01-30 13:15", "impact": "high", "currencies": ["EUR"]},
    {"name": "ECB Rate", "time": "2026-03-05 13:15", "impact": "high", "currencies": ["EUR"]},
    # BOE Rate Decisions
    {"name": "BOE Rate", "time": "2025-05-08 11:00", "impact": "high", "currencies": ["GBP"]},
    {"name": "BOE Rate", "time": "2025-06-19 11:00", "impact": "high", "currencies": ["GBP"]},
    {"name": "BOE Rate", "time": "2025-08-07 11:00", "impact": "high", "currencies": ["GBP"]},
    {"name": "BOE Rate", "time": "2025-09-18 11:00", "impact": "high", "currencies": ["GBP"]},
    {"name": "BOE Rate", "time": "2025-11-06 12:00", "impact": "high", "currencies": ["GBP"]},
    {"name": "BOE Rate", "time": "2025-12-18 12:00", "impact": "high", "currencies": ["GBP"]},
    {"name": "BOE Rate", "time": "2026-02-05 12:00", "impact": "high", "currencies": ["GBP"]},
    {"name": "BOE Rate", "time": "2026-03-19 12:00", "impact": "high", "currencies": ["GBP"]},
    # #66 — RBA Rate Decisions (Australia — AUD)
    {"name": "RBA Rate", "time": "2025-05-06 04:30", "impact": "high", "currencies": ["AUD"]},
    {"name": "RBA Rate", "time": "2025-07-08 04:30", "impact": "high", "currencies": ["AUD"]},
    {"name": "RBA Rate", "time": "2025-08-05 04:30", "impact": "high", "currencies": ["AUD"]},
    {"name": "RBA Rate", "time": "2025-09-23 04:30", "impact": "high", "currencies": ["AUD"]},
    {"name": "RBA Rate", "time": "2025-11-04 03:30", "impact": "high", "currencies": ["AUD"]},
    {"name": "RBA Rate", "time": "2025-12-09 03:30", "impact": "high", "currencies": ["AUD"]},
    {"name": "RBA Rate", "time": "2026-02-17 03:30", "impact": "high", "currencies": ["AUD"]},
    {"name": "RBA Rate", "time": "2026-04-07 04:30", "impact": "high", "currencies": ["AUD"]},
    # #66 — RBNZ Rate Decisions (Nueva Zelanda — NZD)
    {"name": "RBNZ Rate", "time": "2025-05-28 02:00", "impact": "high", "currencies": ["NZD"]},
    {"name": "RBNZ Rate", "time": "2025-07-09 02:00", "impact": "high", "currencies": ["NZD"]},
    {"name": "RBNZ Rate", "time": "2025-08-27 02:00", "impact": "high", "currencies": ["NZD"]},
    {"name": "RBNZ Rate", "time": "2025-10-08 01:00", "impact": "high", "currencies": ["NZD"]},
    {"name": "RBNZ Rate", "time": "2025-11-26 01:00", "impact": "high", "currencies": ["NZD"]},
    {"name": "RBNZ Rate", "time": "2026-02-18 01:00", "impact": "high", "currencies": ["NZD"]},
    {"name": "RBNZ Rate", "time": "2026-04-08 02:00", "impact": "high", "currencies": ["NZD"]},
    # #66 — Fed / CPI 2026 extendido
    {"name": "Fed Rate Decision", "time": "2026-05-06 18:00", "impact": "high", "currencies": ["USD"]},
    {"name": "Fed Rate Decision", "time": "2026-06-17 18:00", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",               "time": "2026-05-12 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "CPI",               "time": "2026-06-10 12:30", "impact": "high", "currencies": ["USD"]},
    # #66 — NFP 2026 extendido
    {"name": "NFP", "time": "2026-06-05 12:30", "impact": "high", "currencies": ["USD"]},
    {"name": "NFP", "time": "2026-07-02 12:30", "impact": "high", "currencies": ["USD"]},
]


def _parse_known_events() -> list[dict]:
    """Convierte KNOWN_EVENTS_UTC a objetos datetime."""
    events = []
    for ev in KNOWN_EVENTS_UTC:
        try:
            dt = datetime.strptime(ev["time"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            events.append({**ev, "datetime": dt})
        except ValueError:
            pass
    return events


def _try_fetch_forexfactory() -> list[dict]:
    """
    Intenta obtener el calendario de ForexFactory.
    Retorna lista vacía si falla (sin API key requerida, pero puede bloquear).
    """
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        events = []
        for ev in data:
            if ev.get("impact") != "High":
                continue
            try:
                # ForexFactory format: "2025-04-18T12:30:00-04:00"
                dt_str = ev.get("date", "")
                if not dt_str:
                    continue
                # Normalizar a UTC
                from datetime import timezone as tz
                dt = datetime.fromisoformat(dt_str).astimezone(timezone.utc)
                events.append({
                    "name": ev.get("title", "?"),
                    "datetime": dt,
                    "impact": "high",
                    "currencies": [ev.get("country", "?")],
                })
            except Exception:
                continue
        return events
    except Exception as e:
        logger.debug(f"ForexFactory no disponible: {e}")
        return []


def get_events_today(now: Optional[datetime] = None) -> list[dict]:
    """
    Retorna eventos de alto impacto para hoy (UTC).
    Primero intenta ForexFactory, luego fallback a hardcoded.
    """
    now = now or datetime.now(timezone.utc)

    # Intentar ForexFactory
    ff_events = _try_fetch_forexfactory()
    if ff_events:
        today_events = [
            e for e in ff_events
            if e["datetime"].date() == now.date()
        ]
        if today_events:
            logger.debug(f"Calendario: {len(today_events)} eventos hoy (ForexFactory)")
            return today_events

    # Fallback: calendario hardcoded
    all_known = _parse_known_events()
    today_events = [
        e for e in all_known
        if e["datetime"].date() == now.date()
    ]
    logger.debug(f"Calendario: {len(today_events)} eventos hoy (hardcoded)")
    return today_events


def is_news_blackout(
    symbol: Optional[str] = None,
    now: Optional[datetime] = None,
    before_min: int = PAUSE_BEFORE_MIN,
    after_min: int = PAUSE_AFTER_MIN,
) -> tuple[bool, str]:
    """
    Verifica si el momento actual está en zona de blackout por noticias.

    Args:
        symbol:    Si se especifica, filtra solo eventos que afectan ese par.
                   Ej: "EURUSD" → afectan EUR o USD.
        now:       Timestamp actual (UTC). Usa datetime.now() si None.
        before_min: Minutos antes del evento para entrar en blackout.
        after_min:  Minutos después del evento para salir de blackout.

    Returns:
        (is_blackout: bool, reason: str)
    """
    now = now or datetime.now(timezone.utc)
    events = get_events_today(now)

    # Extraer divisas del símbolo (ej: "EURUSD" → ["EUR", "USD"])
    symbol_currencies: set[str] = set()
    if symbol and len(symbol) >= 6:
        symbol_currencies = {symbol[:3], symbol[3:6]}

    for event in events:
        ev_time = event["datetime"]
        ev_currencies = set(event.get("currencies", []))

        # Verificar si el evento aplica al símbolo
        if symbol_currencies and not (ev_currencies & symbol_currencies):
            continue

        window_start = ev_time - timedelta(minutes=before_min)
        window_end   = ev_time + timedelta(minutes=after_min)

        if window_start <= now <= window_end:
            reason = (
                f"{event['name']} @ {ev_time.strftime('%H:%M')} UTC "
                f"({ev_currencies}) — blackout {before_min}min antes / {after_min}min después"
            )
            return True, reason

    return False, ""


def get_next_event(now: Optional[datetime] = None) -> Optional[dict]:
    """Retorna el próximo evento de alto impacto del día (o None)."""
    now = now or datetime.now(timezone.utc)
    events = get_events_today(now)
    future = [e for e in events if e["datetime"] > now]
    if not future:
        return None
    return min(future, key=lambda e: e["datetime"])


def log_today_schedule(now: Optional[datetime] = None) -> None:
    """Imprime el calendario del día en el log."""
    now = now or datetime.now(timezone.utc)
    events = get_events_today(now)
    if not events:
        logger.info(f"Calendario: sin eventos de alto impacto hoy ({now.strftime('%Y-%m-%d')})")
        return

    logger.info(f"Calendario — {len(events)} evento(s) de alto impacto hoy:")
    for ev in sorted(events, key=lambda e: e["datetime"]):
        currencies = "/".join(ev.get("currencies", ["?"]))
        logger.info(
            f"  ⚠️  {ev['datetime'].strftime('%H:%M')} UTC | {ev['name']} | {currencies}"
        )
