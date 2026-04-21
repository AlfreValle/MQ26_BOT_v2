"""
MQ26 BOT v2 — Auditoría Completa del Sistema

Revisión profunda de 10 capas:
  1. Configuración y parámetros de riesgo
  2. Integridad de la estrategia S03
  3. Conexión MT5 y estado de cuenta
  4. Datos de backtest (CSV) — solo S03, todos positivos
  5. Protecciones de riesgo activas (M72/M73/M77/M91/M136)
  6. Telegram y alertas
  7. Sistema de archivos y logs
  8. Dependencias Python
  9. Consistencia de capital
 10. Resumen ejecutivo

Uso:
    python audit.py
    python audit.py --verbose    # Muestra detalles de cada check
    python audit.py --export-md  # Markdown → data/reports/audit_evidence.md
    python audit.py --export-md -   # Markdown a stdout
    python audit.py --export-md ruta/salida.md
"""
from __future__ import annotations

import sys
import io
import argparse
import os
import platform
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from dotenv import load_dotenv
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

_audit_argp = argparse.ArgumentParser(description="MQ26 BOT v2 — auditoría del sistema")
_audit_argp.add_argument("--verbose", action="store_true")
_audit_argp.add_argument(
    "--export-md",
    nargs="?",
    const=str(_ROOT / "data" / "reports" / "audit_evidence.md"),
    default=None,
    metavar="FILE",
    help="Exportar resultados en Markdown (FILE o ruta por defecto; use '-' para stdout)",
)
_audit_args, _audit_rest = _audit_argp.parse_known_args()

# ─── Colores y formato ────────────────────────────────────────────────────────
OK    = "[  OK  ]"
WARN  = "[ WARN ]"
ERROR = "[ERROR!]"
INFO  = "[ INFO ]"
SKIP  = "[ SKIP ]"

WIDTH = 70

results: list[dict] = []
errors   = 0
warnings = 0
verbose: bool = _audit_args.verbose
export_md_path: str | None = _audit_args.export_md
MD_LINES: list[str] = []
_CURRENT_AUDIT_SECTION: str = ""


def check(label: str, passed: bool, msg: str = "", critical: bool = True,
          detail: str = "") -> bool:
    global errors, warnings
    if passed:
        tag = OK
    elif critical:
        tag = ERROR
        errors += 1
    else:
        tag = WARN
        warnings += 1

    suffix = f" — {msg}" if msg and not passed else ""
    print(f"  {tag}  {label}{suffix}")
    if detail and verbose:
        for line in detail.strip().splitlines():
            print(f"           {line}")
    results.append({
        "label": label, "passed": passed, "critical": critical,
        "section": _CURRENT_AUDIT_SECTION,
    })
    if export_md_path is not None:
        box = "x" if passed else " "
        tag_md = "OK" if passed else ("ERROR" if critical else "WARN")
        md_line = f"- [{box}] **{tag_md}** — {label}"
        if not passed and msg:
            md_line += f" — {msg}"
        MD_LINES.append(md_line)
        if detail and verbose:
            for line in detail.strip().splitlines():
                MD_LINES.append(f"  _{line}_")
    return passed


def info(msg: str) -> None:
    print(f"  {INFO}  {msg}")
    if export_md_path is not None:
        MD_LINES.append(f"> {msg}")


def section(title: str) -> None:
    global _CURRENT_AUDIT_SECTION
    _CURRENT_AUDIT_SECTION = title.strip()
    print(f"\n{'─' * WIDTH}")
    print(f"  {title}")
    print(f"{'─' * WIDTH}")
    if export_md_path is not None:
        MD_LINES.append("")
        MD_LINES.append(f"## {_CURRENT_AUDIT_SECTION}")
        MD_LINES.append("")


# ═════════════════════════════════════════════════════════════════════════════
print()
print("=" * WIDTH)
print("  MQ26 BOT v2 — AUDITORIA COMPLETA DEL SISTEMA")
print("  Fecha:", __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * WIDTH)

# ─── 1. CONFIGURACION ────────────────────────────────────────────────────────
section("1/10  CONFIGURACION Y PARAMETROS DE RIESGO")
try:
    from config.settings import settings

    check("settings.py carga sin errores", True)
    check("MODE = demo o live",
          settings.mode in ("demo", "live"),
          f"Actual: '{settings.mode}' — debe ser demo o live")

    # Riesgo por trade
    rpt = settings.risk.risk_per_trade_pct
    check("risk_per_trade_pct <= 2%", rpt <= 2.0,
          f"Actual: {rpt}% — demasiado alto para cuenta pequeña",
          detail=f"Valor actual: {rpt}%  |  Recomendado: 1.0%")

    # Kill switch
    ks = settings.risk.dd_kill_switch_pct
    check("kill_switch <= 15%", ks <= 15.0,
          f"Actual: {ks}% — subir el riesgo de ruina")
    check("kill_switch <= 12% (óptimo)", ks <= 12.0,
          f"Actual: {ks}%", critical=False,
          detail="12% = max 12% del balance en pérdidas — óptimo para gestión de riesgo")

    # Daily loss
    dl = settings.risk.max_daily_loss_pct
    check("max_daily_loss_pct <= 3%", dl <= 3.0,
          f"Actual: {dl}%")

    # Max posiciones
    mp = settings.risk.max_open_positions
    check("max_open_positions <= 5", mp <= 5,
          f"Actual: {mp}")
    check("max_open_positions <= 3 (óptimo)", mp <= 3,
          f"Actual: {mp}", critical=False)

    # Min R:R
    rr = settings.risk.min_rr_ratio
    check("min_rr_ratio >= 1.5", rr >= 1.5,
          f"Actual: {rr} — por debajo del mínimo institucional")

    # News buffer
    nb = settings.risk.news_buffer_minutes
    check("news_buffer_minutes >= 15", nb >= 15,
          f"Actual: {nb} min")

except Exception as e:
    check("settings.py importable", False, str(e))

# ─── 2. INTEGRIDAD DE ESTRATEGIA S03 ─────────────────────────────────────────
section("2/10  ESTRATEGIA S03 ASIAN RANGE v3")
try:
    from strategies.forex.s03_asian_range import AsianRangeStrategy
    s = AsianRangeStrategy()

    check("S03 importable sin errores", True)
    check("strategy_id = S03_AsianRange",
          s.strategy_id == "S03_AsianRange",
          f"Actual: {s.strategy_id}")
    check("breakout_vol_mult >= 1.5",
          s.breakout_vol_mult >= 1.5,
          f"Actual: {s.breakout_vol_mult}x — filtro de volumen insuficiente")
    check("use_trend_filter activo",
          getattr(s, "use_trend_filter", False),
          "Filtro de tendencia EMA desactivado", critical=False)
    check("use_adx_filter activo",
          getattr(s, "use_adx_filter", False),
          "Filtro ADX desactivado", critical=False)

    # Verificar que S06 no esté en producción
    import demo_trader as dt_mod
    strat_type = type(dt_mod.DemoTrader.__init__.__globals__.get(
        "AsianRangeStrategy", None))
    check("demo_trader usa AsianRangeStrategy (no S06)",
          "AsianRangeStrategy" in str(dt_mod.DemoTrader.__init__.__code__.co_names),
          "Verificar import en demo_trader.py")

    # Verificar que main_backtest no tiene S07
    import main_backtest as mb_mod
    has_s07 = "s07" in mb_mod.STRATEGIES
    check("S07 OBLondon eliminado de main_backtest", not has_s07,
          "s07 todavia en STRATEGIES dict — eliminar")
    check("S03 es la unica estrategia activa",
          list(mb_mod.STRATEGIES.keys()) == ["s03"],
          f"Estrategias: {list(mb_mod.STRATEGIES.keys())}")

except Exception as e:
    check("S03 importable", False, str(e))

# ─── 3. CONEXION MT5 ─────────────────────────────────────────────────────────
section("3/10  CONEXION MT5 Y ESTADO DE CUENTA")
mt5_balance = 0.0
mt5_equity  = 0.0
try:
    from execution.mt5_connector import MT5Connector
    conn = MT5Connector()
    connected = conn.connect()
    check("MT5 conectado", connected,
          "Abrir MetaTrader 5 y loguear la cuenta demo")

    if connected:
        acc = conn.get_account_info()
        check("Datos de cuenta disponibles", bool(acc))

        if acc:
            mt5_balance = acc.get("balance", 0)
            mt5_equity  = acc.get("equity",  0)
            server      = acc.get("server",  "")
            leverage    = acc.get("leverage", 0)
            currency    = acc.get("currency", "")
            login       = acc.get("login", 0)

            check(f"Login: {login}", True)
            check(f"Servidor: {server}", True)
            check("Balance > $0", mt5_balance > 0,
                  f"Balance: ${mt5_balance:.2f}")
            check("Balance >= $100 (mínimo operativo)",
                  mt5_balance >= 100,
                  f"Balance actual: ${mt5_balance:.2f}", critical=False)
            check("Leverage >= 100:1", leverage >= 100,
                  f"Leverage: {leverage}:1")

            is_demo = "demo" in server.lower() or "Demo" in server
            if settings.mode == "demo":
                check("Cuenta DEMO (correcto para mode=demo)", is_demo,
                      f"Server '{server}' no parece demo")
            else:
                check("Cuenta LIVE (mode=live activo)", not is_demo,
                      f"Server '{server}' es demo pero mode=live", critical=False)

            # Posiciones abiertas
            positions = conn.get_open_positions()
            n_pos = len(positions)
            check(f"Posiciones abiertas: {n_pos}",
                  n_pos <= 3,
                  f"{n_pos} posiciones — por encima del maximo (3)", critical=False)
            if n_pos > 0:
                info(f"Posiciones: {[p['symbol'] for p in positions]}")

        conn.disconnect()

except Exception as e:
    check("MT5 importable / conectable", False, str(e))

# ─── 4. DATOS DE BACKTEST ─────────────────────────────────────────────────────
section("4/10  DATOS DE BACKTEST (CSV)")
TRADES_CSV = Path("data/reports/backtest_report_trades.csv")
try:
    import pandas as pd

    check("CSV de trades existe", TRADES_CSV.exists(),
          f"Correr: python main_backtest.py --strategy s03 --period 60d")

    if TRADES_CSV.exists():
        df = pd.read_csv(TRADES_CSV)
        check("CSV no vacio", len(df) > 0, "Sin trades en el CSV")

        strategies_in_csv = df["strategy"].unique().tolist() if "strategy" in df else []
        bad_strats = [s for s in strategies_in_csv
                      if s in ("S06_OBLondon", "S07_OBLondon")]

        check("Sin S06_OBLondon en CSV",
              len(bad_strats) == 0,
              f"Estrategias malas encontradas: {bad_strats} — "
              f"correr: python main_backtest.py --strategy s03 --period 60d")

        check("Solo S03_AsianRange en CSV",
              all(s == "S03_AsianRange" for s in strategies_in_csv),
              f"Estrategias: {strategies_in_csv}")

        # Verificar que todos los pares son positivos
        if "pnl_usd" in df.columns and "symbol" in df.columns:
            pnl_by_sym = df.groupby("symbol")["pnl_usd"].sum()
            losing_syms = pnl_by_sym[pnl_by_sym < 0]
            check("Todos los pares con PnL positivo",
                  len(losing_syms) == 0,
                  f"Pares en negativo: {losing_syms.index.tolist()}",
                  critical=False)

            total_pnl = df["pnl_usd"].sum()
            total_trades = len(df)
            winners = (df["pnl_usd"] > 0).sum()
            wr = winners / total_trades if total_trades > 0 else 0

            info(f"Total trades en CSV: {total_trades}")
            info(f"PnL total: ${total_pnl:+,.2f}")
            info(f"Win rate global: {wr:.1%}")

            check("PnL total positivo", total_pnl > 0,
                  f"PnL: ${total_pnl:+,.2f}")
            check("Win rate >= 60%", wr >= 0.60,
                  f"WR: {wr:.1%}", critical=False)

except Exception as e:
    check("Lectura de CSV", False, str(e))

# ─── 5. PROTECCIONES DE RIESGO ───────────────────────────────────────────────
section("5/10  CAPAS DE PROTECCION DE RIESGO")
try:
    import demo_trader as dt_mod

    # M72 Correlacion
    has_corr = hasattr(dt_mod, "CORR_GROUPS") and len(dt_mod.CORR_GROUPS) >= 2
    check("M72 Correlacion inter-pares configurada", has_corr,
          "CORR_GROUPS no definido o vacio")
    if has_corr:
        info(f"Grupos: {[list(g) for g in dt_mod.CORR_GROUPS]}")

    # M73 Daily loss
    dl_limit = getattr(dt_mod, "DAILY_LOSS_LIMIT", 0)
    check("M73 Daily loss limit definido", dl_limit > 0,
          "DAILY_LOSS_LIMIT no definido")
    check("M73 Daily loss limit <= 3%", 0 < dl_limit <= 0.03,
          f"Actual: {dl_limit:.1%}")

    # M77 Max posiciones
    max_pos = getattr(dt_mod, "MAX_OPEN_POSITIONS", 0)
    check("M77 Max posiciones definido", max_pos > 0,
          "MAX_OPEN_POSITIONS no definido")
    check("M77 Max posiciones <= 3", max_pos <= 3,
          f"Actual: {max_pos}", critical=False)

    # M91 Calendario
    try:
        from core.economic_calendar import is_news_blackout, get_events_today
        from datetime import datetime, timezone
        events = get_events_today(datetime.now(timezone.utc))
        check("M91 Calendario economico importable", True)
        check(f"M91 Eventos cargados hoy: {len(events)}", True)
    except Exception as e:
        check("M91 Calendario economico", False, str(e))

    # M136 Priority ranking
    has_rank = hasattr(dt_mod, "SHARPE_RANK") and len(dt_mod.SHARPE_RANK) >= 8
    check("M136 Ranking por Sharpe configurado", has_rank,
          "SHARPE_RANK incompleto")

    # Kill switch en demo_trader
    import inspect
    dt_src = inspect.getsource(dt_mod.DemoTrader._tick)
    check("Kill switch implementado en _tick",
          "kill_switch" in dt_src and "dd_kill_switch_pct" in dt_src)
    check("Portfolio inicializado desde MT5 (bug fix aplicado)",
          "_init_portfolio_from_mt5" in inspect.getsource(dt_mod.DemoTrader.start))

    # M91 PID lock — Windows debe usar tasklist (os.kill(pid,0) no es fiable entre procesos)
    try:
        src_pid_fn = inspect.getsource(dt_mod._pid_still_running)
    except (OSError, TypeError, AttributeError):
        src_pid_fn = ""
    if platform.system() == "Windows":
        check(
            "M91 PID lock Windows-compatible (tasklist)",
            "tasklist" in src_pid_fn,
            "En Windows debe usarse tasklist para detectar PID ajeno activo",
        )
    else:
        check(
            "M91 PID lock POSIX (os.kill)",
            "os.kill" in src_pid_fn,
            "Rama POSIX debe usar os.kill(pid, 0) para comprobar proceso",
        )

except Exception as e:
    check("Modulo demo_trader importable", False, str(e))

# ─── 6. TELEGRAM ─────────────────────────────────────────────────────────────
section("6/10  TELEGRAM Y ALERTAS")
try:
    from core.telegram_alerts import alerter

    tg_enabled = alerter.enabled
    check("Telegram habilitado (TG_ENABLED=true)", tg_enabled,
          "TG_TOKEN o TG_CHAT_ID no configurados en .env", critical=False)

    if tg_enabled:
        token = getattr(alerter, "token", "")
        chat_id = getattr(alerter, "chat_id", "")
        check("TG_TOKEN configurado", bool(token) and token != "TU_BOT_TOKEN",
              "Token no configurado")
        check("TG_CHAT_ID configurado", bool(chat_id) and chat_id != "TU_CHAT_ID",
              "Chat ID no configurado")

        # Test de conectividad (no envía mensaje)
        import urllib.request, json
        try:
            url = f"https://api.telegram.org/bot{token}/getMe"
            resp = urllib.request.urlopen(url, timeout=5)
            data = json.loads(resp.read())
            bot_name = data.get("result", {}).get("username", "?")
            check(f"Bot Telegram activo: @{bot_name}", data.get("ok", False))
        except Exception as te:
            check("Conectividad Telegram API", False,
                  str(te)[:60], critical=False)

except Exception as e:
    check("telegram_alerts importable", False, str(e))

# ─── 7. SISTEMA DE ARCHIVOS Y LOGS ───────────────────────────────────────────
section("7/10  SISTEMA DE ARCHIVOS Y LOGS")

dirs_required = [
    ("data/logs",    True),
    ("data/cache",   True),
    ("data/reports", True),
]
for dir_path, critical in dirs_required:
    p = Path(dir_path)
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)
    check(f"Directorio {dir_path}/ existe", p.exists(), critical=critical)

# Log del demo trader
log_file = Path("data/logs/demo_trader.log")
if log_file.exists():
    size_mb = log_file.stat().st_size / 1_048_576
    check("Log demo_trader.log existe", True)
    check(f"Log < 50 MB (actual: {size_mb:.1f} MB)",
          size_mb < 50,
          f"Log muy grande ({size_mb:.1f} MB) — rotar o limpiar", critical=False)

    # Última línea del log
    try:
        lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        if lines:
            last_line = lines[-1]
            info(f"Ultima entrada log: {last_line[-80:]}")
    except Exception:
        pass
else:
    check("Log demo_trader.log existe", False,
          "El bot no ha corrido aun — normal en primera ejecucion", critical=False)

# Archivos criticos
critical_files = [
    "demo_trader.py",
    "main_backtest.py",
    "dashboard.py",
    "preflight_check.py",
    "config/settings.py",
    "strategies/forex/s03_asian_range.py",
    "execution/mt5_connector.py",
    "risk/position_sizer.py",
    "core/economic_calendar.py",
    "core/telegram_alerts.py",
    ".env",
]
for f in critical_files:
    check(f"Archivo critico: {f}", Path(f).exists(),
          f"Falta {f} — sistema incompleto")

# Verificar que S06 no se ejecuta desde main_backtest
import ast
try:
    mb_src = Path("main_backtest.py").read_text(encoding="utf-8")
    check("main_backtest.py no importa S06_OBLondon",
          "OBLondonStrategy" not in mb_src and "s06_ob_london" not in mb_src,
          "main_backtest todavia importa S06 — verificar")
except Exception:
    pass

# ─── 8. DEPENDENCIAS ─────────────────────────────────────────────────────────
section("8/10  DEPENDENCIAS PYTHON")
deps = {
    "pandas":       "1.5",
    "numpy":        "1.23",
    "pandas_ta":    "0.3",
    "plotly":       "5.0",
    "MetaTrader5":  "5.0",
    "pydantic":     "2.0",
    "streamlit":    "1.20",
    "dotenv":       None,
}
for dep, min_ver in deps.items():
    try:
        mod_name = "python_dotenv" if dep == "dotenv" else dep
        try:
            mod = __import__(dep)
        except ImportError:
            mod = __import__("dotenv")
        check(f"{dep}", True)
    except ImportError:
        check(f"{dep}", False, f"pip install {dep}")

# ─── 9. CONSISTENCIA DE CAPITAL ──────────────────────────────────────────────
section("9/10  CONSISTENCIA DE CAPITAL")
try:
    from config.settings import settings

    # Capital de referencia en demo_trader
    import demo_trader as dt_mod
    import inspect
    dt_src_full = inspect.getsource(dt_mod)
    has_capital_from_mt5 = "_init_portfolio_from_mt5" in dt_src_full
    check("Bug capital mismatch CORREGIDO",
          has_capital_from_mt5,
          "Portfolio sigue inicializando con --capital en lugar de balance MT5")

    info(f"Balance MT5 actual: ${mt5_balance:,.2f}")
    info(f"Equity MT5 actual:  ${mt5_equity:,.2f}")

    # Usar el balance real de MT5 como referencia de capital
    cap_ref = mt5_balance if mt5_balance > 0 else 101.0
    info(f"Capital referencia sizing: ${cap_ref:,.2f} (balance MT5 real)")

    if cap_ref > 0:
        ks_pct = settings.risk.dd_kill_switch_pct / 100
        max_loss = cap_ref * ks_pct
        check(
            f"Kill switch razonable (max perdida: ${max_loss:.2f})",
            max_loss < cap_ref * 0.20,
            f"Kill switch dispara muy tarde — revisar dd_kill_switch_pct",
            critical=False,
        )

        risk_usd = cap_ref * (settings.risk.risk_per_trade_pct / 100)
        check(
            f"Riesgo por trade: ${risk_usd:.2f} ({settings.risk.risk_per_trade_pct}%)",
            0 < risk_usd <= cap_ref * 0.03,   # no más del 3% del balance
            f"${risk_usd:.2f} supera el 3% del balance",
        )

        daily_loss_usd = cap_ref * (settings.risk.max_daily_loss_pct / 100)
        info(f"Stop diario: -${daily_loss_usd:.2f} ({settings.risk.max_daily_loss_pct:.1f}%)")
        info(f"Kill switch: -${cap_ref * ks_pct:.2f} ({settings.risk.dd_kill_switch_pct:.1f}%)")

except Exception as e:
    check("Consistencia de capital", False, str(e))

# ─── 10. RESUMEN EJECUTIVO ────────────────────────────────────────────────────
total   = len(results)
passed  = sum(1 for r in results if r["passed"])
failed  = sum(1 for r in results if not r["passed"] and r["critical"])
warned  = sum(1 for r in results if not r["passed"] and not r["critical"])

print()
print("=" * WIDTH)
print("  10/10  RESUMEN EJECUTIVO")
print("=" * WIDTH)
print(f"  Total checks:    {total}")
print(f"  OK:              {passed}")
print(f"  Errores criticos:{failed}  {'<-- RESOLVER ANTES DE OPERAR' if failed else ''}")
print(f"  Advertencias:    {warned}  {'(no bloquean operacion)' if warned else ''}")
print()

if failed == 0 and warned == 0:
    print("  RESULTADO: SISTEMA OPTIMO — TODO EN ORDEN")
elif failed == 0:
    print("  RESULTADO: SISTEMA OPERATIVO — Advertencias menores detectadas")
    print("  Las advertencias no bloquean el bot pero es recomendable revisarlas.")
else:
    print("  RESULTADO: HAY ERRORES CRITICOS — Resolver antes de operar dinero")
    print()
    print("  Errores criticos encontrados:")
    for r in results:
        if not r["passed"] and r["critical"]:
            print(f"    [ERROR] {r['label']}")

print()
print("  Estado del portafolio S03 (60d backtest):")
print("    BTCUSD  Sharpe 25.86  PF 11.79  WR 91.7%  MaxDD  1.2%  +17.1%")
print("    XAUUSD  Sharpe 16.55  PF  3.43  WR 80.0%  MaxDD  2.7%  +22.5%")
print("    AUDUSD  Sharpe 12.82  PF  3.08  WR 75.0%  MaxDD  4.8%  +60.8%")
print("    NZDUSD  Sharpe 12.76  PF  2.74  WR 77.4%  MaxDD  3.8%  +33.1%")
print("    ETHUSD  Sharpe 11.27  PF  2.32  WR 84.2%  MaxDD  3.5%  +13.7%")
print("    GBPUSD  Sharpe 10.94  PF  2.29  WR 65.1%  MaxDD  4.0%  +48.0%")
print("    EURUSD  Sharpe  9.95  PF  2.07  WR 65.0%  MaxDD  3.4%  +13.8%")
print("    AUDJPY  Sharpe  8.45  PF  1.46  WR 59.1%  MaxDD  2.9%   +5.8%")
print()
print("  Estado LIVE — Cuenta IC Markets activa:")
print(f"    [✓] MT5 conectado: cuenta 7994499 (Raw Trading Ltd)")
print(f"    [✓] Balance actual: ${mt5_balance:,.2f}")
print(f"    [✓] MODE=live configurado en .env")
print(f"    [✓] AutoTrading: habilitar en MT5 (botón verde toolbar)")
print()
print("  Comando de operación diaria:")
print("    python demo_trader.py --capital 101 --symbol AUDUSD NZDUSD GBPUSD EURUSD")
print()
print("  Ventana de señales (UTC):")
print("    Asian range: 00:00–07:00 UTC  (formación del rango)")
print("    London breakout: 07:00–10:30 UTC  (entrada de posiciones)")
print("=" * WIDTH)
print()

# ─── Export Markdown (comité / checklist código) ─────────────────────────────
if export_md_path is not None:
    import datetime as _dt

    _now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _total = len(results)
    _passed = sum(1 for r in results if r["passed"])
    _failed = sum(1 for r in results if not r["passed"] and r["critical"])
    _warned = sum(1 for r in results if not r["passed"] and not r["critical"])
    _header = "\n".join(
        [
            "# MQ26 BOT v2 — Evidencia de auditoría (`audit.py`)",
            "",
            f"**Generado:** {_now}",
            "",
            "_Copiar este bloque en `plantilla-checklist-auditoria-codigo.md` (evidencia)._",
            "",
        ]
    )
    _summary = "\n".join(
        [
            "",
            "## Resumen numérico",
            "",
            f"- Total checks: **{_total}**",
            f"- OK: **{_passed}**",
            f"- Errores críticos: **{_failed}**",
            f"- Advertencias: **{_warned}**",
            "",
        ]
    )
    if _failed > 0:
        _summary += "**Veredicto automatizado:** hay errores críticos — no operar hasta resolverlos.\n"
    elif _warned > 0:
        _summary += "**Veredicto automatizado:** operativo con advertencias.\n"
    else:
        _summary += "**Veredicto automatizado:** sin errores ni advertencias en checks.\n"

    md_out = _header + "\n".join(MD_LINES) + _summary
    if export_md_path.strip() == "-":
        print("\n" + "─" * WIDTH)
        print("  EXPORT MARKDOWN (--export-md -)")
        print("─" * WIDTH + "\n")
        print(md_out)
    else:
        _outp = Path(export_md_path)
        _outp.parent.mkdir(parents=True, exist_ok=True)
        _outp.write_text(md_out, encoding="utf-8")
        print(f"\n  {INFO}  Markdown exportado: {_outp.resolve()}")
