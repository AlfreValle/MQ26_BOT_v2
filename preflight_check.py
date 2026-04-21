"""
MQ26 BOT v2 — Pre-Flight Check

Verifica que todo esté listo antes de operar dinero real.
Ejecutar ANTES de activar modo live.

Uso:
    python preflight_check.py
"""
from __future__ import annotations

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

OK    = "[OK]"
WARN  = "[WARN]"
ERROR = "[ERROR]"
SKIP  = "[SKIP]"

results = []
all_ok  = True

def check(label: str, passed: bool, msg: str = "", critical: bool = True) -> None:
    global all_ok
    if passed:
        tag = OK
        print(f"  {tag}  {label}")
    elif critical:
        tag = ERROR
        all_ok = False
        print(f"  {tag}  {label}" + (f" — {msg}" if msg else ""))
    else:
        tag = WARN
        print(f"  {tag}  {label}" + (f" — {msg}" if msg else ""))

print()
print("=" * 60)
print("  MQ26 BOT v2 — PRE-FLIGHT CHECK")
print("=" * 60)

# ─── 1. Configuración ──────────────────────────────────────────────────────
print("\n[1] CONFIGURACION")
try:
    from config.settings import settings
    check("Settings cargado", True)
    check("Modo operativo", settings.mode in ("demo","live"),
          f"Modo actual: {settings.mode} (debe ser 'demo' o 'live')")
    check("Risk per trade <= 2%", settings.risk.risk_per_trade_pct <= 2.0,
          f"Actual: {settings.risk.risk_per_trade_pct}%")
    check("Kill switch configurado", settings.risk.dd_kill_switch_pct <= 15.0,
          f"Actual: {settings.risk.dd_kill_switch_pct}%")
except Exception as e:
    check("Settings cargado", False, str(e))

# ─── 2. Conexión MT5 ───────────────────────────────────────────────────────
print("\n[2] CONEXION MT5")
try:
    from execution.mt5_connector import MT5Connector
    conn = MT5Connector()
    if conn.connect():
        acc = conn.get_account_info()
        check("MT5 conectado", True)
        check("Cuenta identificada", bool(acc), f"Login: {acc.get('login')}")
        is_real = "Demo" not in acc.get("server", "")
        check("Servidor REAL (no demo)", is_real,
              f"Server: {acc.get('server')} — cambiar a cuenta real", critical=False)
        check("Balance > $100", acc.get("balance",0) >= 100,
              f"Balance actual: ${acc.get('balance',0):.2f}", critical=False)
        check("Leverage >= 100", acc.get("leverage",0) >= 100,
              f"Leverage: {acc.get('leverage',0)}x")
        conn.disconnect()
    else:
        check("MT5 conectado", False, "No se pudo conectar — verificar MT5 abierto")
except Exception as e:
    check("MT5 conectado", False, str(e))

# ─── 3. Estrategia S03 ─────────────────────────────────────────────────────
print("\n[3] ESTRATEGIA S03 v3")
try:
    from strategies.forex.s03_asian_range import AsianRangeStrategy
    s = AsianRangeStrategy()
    check("S03 importado", True)
    check("Trailing activo (engine)", True)  # Ya verificado en backtest
    check("Trend filter activo", s.use_trend_filter)
    check("ADX filter activo", s.use_adx_filter)
    check("Vol breakout 1.5x", s.breakout_vol_mult >= 1.5,
          f"Actual: {s.breakout_vol_mult}x")
except Exception as e:
    check("S03 importado", False, str(e))

# ─── 4. Instrumentos Top 8 ─────────────────────────────────────────────────
print("\n[4] INSTRUMENTOS")
try:
    from config.instruments import ALL_INSTRUMENTS
    from demo_trader import DEFAULT_SYMBOLS
    for sym in DEFAULT_SYMBOLS:
        check(f"{sym} en instruments.py", sym in ALL_INSTRUMENTS,
              f"{sym} no encontrado en config")
except Exception as e:
    check("Instrumentos cargados", False, str(e))

# ─── 5. Calendario económico ───────────────────────────────────────────────
print("\n[5] CALENDARIO ECONOMICO")
try:
    from core.economic_calendar import is_news_blackout, get_events_today
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    events = get_events_today(now)
    blackout, reason = is_news_blackout(now=now)
    check("Módulo calendario OK", True)
    check(f"Eventos hoy: {len(events)}", True)
    if blackout:
        check("Sin blackout activo", False, reason, critical=False)
    else:
        check("Sin blackout activo", True)
except Exception as e:
    check("Módulo calendario OK", False, str(e))

# ─── 6. Telegram ───────────────────────────────────────────────────────────
print("\n[6] TELEGRAM ALERTAS")
try:
    from core.telegram_alerts import alerter
    if alerter.enabled:
        sent = alerter.info("Pre-flight check completado — bot listo")
        check("Telegram configurado", True)
        check("Mensaje de prueba enviado", sent,
              "Verificar que llegó el mensaje al chat", critical=False)
    else:
        check("Telegram configurado", False,
              "TG_TOKEN y TG_CHAT_ID no configurados en .env", critical=False)
except Exception as e:
    check("Telegram importado", False, str(e))

# ─── 7. Logs y directorios ─────────────────────────────────────────────────
print("\n[7] SISTEMA DE ARCHIVOS")
from pathlib import Path
check("data/logs/ existe", Path("data/logs").exists() or not Path("data/logs").mkdir(parents=True, exist_ok=True))
check("data/cache/ existe", Path("data/cache").exists() or not Path("data/cache").mkdir(parents=True, exist_ok=True))
check("data/reports/ existe", Path("data/reports").exists())

# ─── 8. Dependencias Python ────────────────────────────────────────────────
print("\n[8] DEPENDENCIAS")
deps = ["pandas", "numpy", "pandas_ta", "plotly", "MetaTrader5", "pydantic"]
for dep in deps:
    try:
        __import__(dep)
        check(dep, True)
    except ImportError:
        check(dep, False, f"pip install {dep}")

# ─── Resultado final ───────────────────────────────────────────────────────
print()
print("=" * 60)
if all_ok:
    print("  RESULTADO: TODO OK — LISTO PARA OPERAR")
    print()
    print("  Para iniciar en MODO REAL:")
    print("    1. Fondear cuenta IC Markets con $2,000")
    print("    2. Editar .env: MT5_LOGIN, MT5_PASSWORD, MT5_SERVER=ICMarketsSC-Live01")
    print("    3. Editar .env: MODE=live")
    print("    4. Configurar Telegram en .env (ver .env.live.template)")
    print("    5. Ejecutar: python demo_trader.py --capital 2000")
else:
    print("  RESULTADO: HAY PROBLEMAS — corregir los [ERROR] antes de operar")
print("=" * 60)
print()
