"""
MQ26 BOT v2 — Demo Trading Loop  (S03 v3)

Portafolio Top 8 validado — S03 Asian Range v3 (60d M5):
  BTCUSD  Sharpe 25.86  PF 11.79  WR 91.7%  — 24/7 (crypto)
  XAUUSD  Sharpe 16.55  PF  3.43  WR 80.0%  — Lunes a Viernes (Oro)
  AUDUSD  Sharpe 12.82  PF  3.08  WR 75.0%  — Lunes a Viernes
  NZDUSD  Sharpe 12.76  PF  2.74  WR 77.4%  — Lunes a Viernes
  ETHUSD  Sharpe 12.09  PF  2.55  WR 86.4%  — 24/7 (crypto)
  GBPUSD  Sharpe 10.94  PF  2.29  WR 65.1%  — Lunes a Viernes
  EURUSD  Sharpe  9.95  PF  2.07  WR 65.0%  — Lunes a Viernes
  AUDJPY  Sharpe  8.45  PF  1.46  WR 59.1%  — Lunes a Viernes

Mejoras de riesgo implementadas:
  M72 — Correlación inter-pares: AUDUSD+NZDUSD reducen size a 60%
  M73 — Daily loss limit: pausa si pérdida del día > 2% del capital
  M77 — Máximo 3 posiciones simultáneas (configurable)
  M136 — Signal priority: ejecuta primero el par de mayor Sharpe
  #84 — Consecutive Win Scaling: hasta ×2.0 tras 6+ wins consecutivos
  #94 — Pyramiding: añade 50% de lot a posiciones ganadoras (entre TP1 y TP2)
  #95 — NY Open Breakout: S03 cubre 3 sesiones (Asian / London / NY Open)

Uso:
    python demo_trader.py                      # Corre los 8 ganadores
    python demo_trader.py --symbol BTCUSD      # Solo un símbolo
    python demo_trader.py --dry-run            # Solo loguea señales, sin órdenes
    python demo_trader.py --capital 2000       # Capital de referencia para sizing

NOTA: El drawdown se calcula siempre sobre el balance REAL de MT5, no sobre --capital.
      El argumento --capital solo afecta el tamaño de las posiciones (risk_usd = capital * 1%).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

Path("data/logs").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/logs/demo_trader.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("demo_trader")

import pandas as pd

from config.instruments import ALL_INSTRUMENTS as INSTRUMENTS
from config.settings import settings
from execution.mt5_connector import MT5Connector
from risk.position_sizer import PortfolioState, PositionSizer
from strategies.forex.s03_asian_range import AsianRangeStrategy
from strategies.base import Signal
from core.economic_calendar import is_news_blackout, log_today_schedule
from core.telegram_alerts import alerter as tg
from core.trade_journal import journal as trade_journal


# ─── Portafolio Top 8 — S03v3 (60d M5, trailing ATR, todos PF > 1) ──────────

DEFAULT_SYMBOLS = [
    # ── ELITE (S03v3 60d M5) — todos con PF > 1 y Sharpe > 0 ───────────────
    "BTCUSD",   # Sharpe 25.86 | PF 11.79 | WR 91.7% | 24/7
    "XAUUSD",   # Sharpe 16.55 | PF  3.43 | WR 80.0% | Lun-Vie (Oro)
    "AUDUSD",   # Sharpe 12.82 | PF  3.08 | WR 75.0% | Lun-Vie
    "NZDUSD",   # Sharpe 12.76 | PF  2.74 | WR 77.4% | Lun-Vie
    "ETHUSD",   # Sharpe 12.09 | PF  2.55 | WR 86.4% | 24/7
    "GBPUSD",   # Sharpe 10.94 | PF  2.29 | WR 65.1% | Lun-Vie
    "EURUSD",   # Sharpe  9.95 | PF  2.07 | WR 65.0% | Lun-Vie
    "AUDJPY",   # Sharpe  8.45 | PF  1.46 | WR 59.1% | Lun-Vie
    # ── EXCLUIDOS (PF < 1): GBPJPY, EURJPY, CHFJPY, NZDJPY ─────────────────
]

# Sharpe histórico por símbolo — S03 v4 (60d M5) para priority ranking (M136)
SHARPE_RANK: dict[str, float] = {
    "AUDUSD": 29.20,   # WR 100% | PF ∞   | MaxDD 0.0%
    "NZDUSD": 26.18,   # WR 100% | PF ∞   | MaxDD 0.0%
    "BTCUSD": 19.04,   # WR  88.9% | PF 17.75 | MaxDD 1.2%
    "GBPUSD": 17.92,   # WR  85.0% | PF 12.23 | MaxDD 2.6%
    "EURUSD": 17.32,   # WR  85.7% | PF 11.63 | MaxDD 1.6%
    "XAUUSD": 14.92,   # WR  78.9% | PF  6.03 | MaxDD 2.0%
    "ETHUSD": 10.34,   # WR  85.7% | PF  4.47 | MaxDD 3.5%
    "AUDJPY":  7.20,   # WR 100.0% | PF ∞    | MaxDD 0.0%
}

# Símbols que operan 24/7 — nunca se bloquean por fin de semana
CRYPTO_SYMBOLS: set[str] = {"BTCUSD", "ETHUSD", "SOLUSD"}

# M72 — Grupos de alta correlación: solo 1 señal activa por grupo
CORR_GROUPS: list[set[str]] = [
    {"AUDUSD", "NZDUSD"},      # correlación ~0.93
    {"EURUSD", "GBPUSD"},      # correlación ~0.85
]

TIMEFRAME_SIGNAL  = "M5"
TIMEFRAME_CONTEXT = "H1"
BARS_SIGNAL       = 500   # ~41 horas de M5
BARS_CONTEXT      = 720   # 30 días de H1

LOOP_INTERVAL_SEC  = 300  # Cada 5 minutos
MAX_OPEN_POSITIONS = 3    # M77 — máximo simultáneas
# #76 — Tiered Daily Loss Limits (reemplaza el flat 2% de M73)
DAILY_LOSS_WARN    = 0.015  # 1.5% → advertencia, reducir size al 50%
DAILY_LOSS_LIMIT   = 0.02   # 2.0% → pausar nuevas entradas
DAILY_LOSS_STOP    = 0.03   # 3.0% → cerrar posiciones abiertas y detener
MAX_SIGNAL_AGE_H   = 2.0  # #51 Staleness: señales > 2h se descartan (no ejecutar scalps asiáticos en sesión NY)

BARS_H4            = 120  # #55 H4 macro filter — 120 barras H4 ≈ 20 días
BE_TRIGGER_R       = 0.6  # #52 Move SL to BE cuando profit >= 60% del riesgo inicial
FRIDAY_CLOSE_UTC   = 20   # #59 Hora UTC del viernes para cerrar posiciones FX


def is_market_open(symbol: str, now: datetime) -> bool:
    """
    Verifica si el mercado del símbolo está abierto ahora.
    - Crypto (BTCUSD, ETHUSD, etc.): siempre abierto, 24/7.
    - Forex/Índices/Oro: cerrado sábado 22:00 UTC → domingo 22:00 UTC.
    """
    if symbol in CRYPTO_SYMBOLS:
        return True

    wd = now.weekday()  # 0=Lunes … 5=Sábado, 6=Domingo
    h  = now.hour

    if wd == 5:                  # Sábado — siempre cerrado
        return False
    if wd == 6 and h < 22:       # Domingo antes de las 22:00 UTC
        return False
    if wd == 4 and h >= 22:      # Viernes desde las 22:00 UTC
        return False

    return True


def _pid_still_running(pid: int) -> bool:
    """
    Comprueba si el proceso `pid` sigue activo.
    En Windows `os.kill(pid, 0)` no es fiable para PIDs de otros procesos; se usa tasklist.
    """
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            out = (r.stdout or "") + (r.stderr or "")
            if not out.strip():
                return False
            if "no tasks" in out.lower() or "no hay tareas" in out.lower():
                return False
            first = out.strip().splitlines()[0] if out.strip() else ""
            return str(pid) in first and "Image Name" not in first
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class DemoTrader:
    """
    Orquestador de trading demo. Ejecuta S03v3 sobre datos MT5 en vivo.
    Implementa mejoras M72 (correlación), M73 (daily loss), M77 (max pos), M136 (priority).
    """

    def __init__(self, symbols: list[str], dry_run: bool = False, capital: float = 2000.0):
        self.symbols   = symbols
        self.dry_run   = dry_run
        self.connector = MT5Connector()
        self.strategy  = AsianRangeStrategy()

        # Capital de referencia para sizing (del argumento --capital)
        # El portfolio se inicializa desde el balance REAL de MT5 en start()
        self.capital = capital
        self.portfolio: PortfolioState | None = None
        self.sizer:    PositionSizer    | None = None

        # Señales ya operadas hoy (evitar duplicados)
        # Se reinicia en cada reset diario Y al arrancar el bot
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._traded_today: set[str] = set()
        self._last_date: str = today_str   # inicializar con hoy, no vacío

        # M73/#76 — Pérdida diaria acumulada (tiered limits)
        self._equity_at_day_open: float = 0.0
        self._daily_paused: bool = False
        self._daily_warned: bool = False        # #76 Nivel 1: advertencia activa
        self._daily_hard_stopped: bool = False  # #76 Nivel 3: stop total activo

        # #15 — Consecutive losses pause
        self._consecutive_losses: int = 0
        self._consec_pause_until: float = 0.0   # timestamp hasta cuándo pausar

        # #84 — Consecutive Win Scaling: escalar size tras racha ganadora
        self._consecutive_wins: int = 0         # trades ganadores consecutivos

        # #47 — Heartbeat Telegram cada 6 horas
        self._last_heartbeat: float = 0.0

        # #44 — State persistence: archivo para recuperar estado tras crash
        self._state_file = Path("data/logs/bot_state.json")

        # #24 — Correlación dinámica: caché de precios para calcular correlación
        self._corr_cache: dict[str, list[float]] = {}   # symbol → últimos 20d close H1
        self._corr_matrix: dict[str, dict[str, float]] = {}  # symbol → {symbol2: corr}
        self._corr_last_update: float = 0.0

        # #52/#53 — Position management: rastrear posiciones abiertas para BE y TP1
        # key=ticket, value={"entry": float, "sl_orig": float, "tp1": float,
        #                     "tp2": float, "direction": str, "lot": float,
        #                     "be_done": bool, "tp1_done": bool,
        #                     "pyramid_done": bool, "is_pyramid": bool}  ← #94
        self._managed_positions: dict[int, dict] = {}

        # #60 — Detección de cierres: rastrear tickets previos para detectar trades cerrados
        self._prev_tickets: set[int] = set()
        self._prev_positions_map: dict[int, dict] = {}

        # #59 — Friday auto-close: bandera para evitar doble ejecución
        self._friday_closed_today: bool = False

        # #85 — Symbol Performance Auto-Ranking: re-rankear semanalmente
        self._sharpe_rank_last_update: float = 0.0

        # #88 — Anti-Tilt Short Cooldown: enfriamiento de 1h tras 2 pérdidas en < 2h
        self._tilt_losses: list[float] = []   # timestamps de pérdidas recientes
        self._tilt_cooldown_until: float = 0.0

        # #90 — Weekly P&L Scale-Down: si semana negativa > 3%, reducir size
        self._weekly_scale: float = 1.0       # 1.0 = normal, 0.5 = protección semanal
        self._weekly_scale_last_check: float = 0.0

        # #71 — Equity Curve Smoothing: historial de equity por tick (max 50 ticks)
        self._equity_history: list[float] = []
        self._equity_regime: str = "normal"   # "normal" | "bearish" (equity < MA20)

        # #72 — Auto-Blacklist por pérdidas consecutivas por símbolo
        # {symbol: {"losses": int, "paused_until": float}}
        self._symbol_losses: dict[str, dict] = {s: {"losses": 0, "paused_until": 0.0} for s in symbols}

        # Funnel de señales (KPI comité / checklist financiera)
        self._signal_funnel: dict[str, int] = {
            "generated": 0,
            "filtered_spread": 0,
            "filtered_staleness": 0,
            "filtered_session": 0,
            "executed": 0,
        }
        self._FUNNEL_JSON = Path("data/logs/signal_funnel.json")

        logger.info(f"DemoTrader inicializado | Símbolos: {symbols} | Capital ref: ${capital:.0f} | DryRun: {dry_run}")
        logger.info(f"Mejoras activas: M72-correlación | M73-daily_loss_2% | M77-max3pos | M136-priority")
        tg.info(f"MQ26 BOT iniciado | ref ${capital:.0f} | {'DRY RUN' if dry_run else 'LIVE'} | {len(symbols)} símbolos")

    # ─── Loop principal ───────────────────────────────────────────────────────

    def _init_portfolio_from_mt5(self) -> None:
        """
        Inicializa PortfolioState desde el balance REAL de la cuenta MT5.
        Esto evita el bug donde --capital=2000 pero balance real=$300 → DD=85%.
        El argumento --capital se usa solo como referencia de sizing, no como peak_equity.
        """
        acc = self.connector.get_account_info()
        if acc and acc.get("equity", 0) > 0:
            real_equity = acc["equity"]
            real_balance = acc["balance"]
            logger.info(
                f"Portfolio inicializado desde MT5 | Balance=${real_balance:.2f} | "
                f"Equity=${real_equity:.2f} | Capital ref (sizing): ${self.capital:.0f}"
            )
            if abs(real_equity - self.capital) > self.capital * 0.1:
                logger.warning(
                    f"AVISO: Capital MT5 (${real_equity:.0f}) difiere del --capital "
                    f"(${self.capital:.0f}). El portfolio usará el balance REAL para "
                    f"calcular drawdown. El --capital solo se usa para el sizing de posiciones."
                )
        else:
            # Fallback: sin datos MT5 (dry-run o error), usar --capital
            real_equity = self.capital
            logger.warning(f"Sin datos de cuenta MT5 — usando capital ref ${self.capital:.0f} para portfolio")

        self.portfolio = PortfolioState(
            capital=real_equity,
            equity=real_equity,
            peak_equity=real_equity,
        )
        self.sizer = PositionSizer(self.portfolio)
        self._equity_at_day_open = real_equity

    # ─── #91 PID Lock — prevenir instancias múltiples ───────────────────────

    _PID_FILE = Path("data/logs/bot.pid")

    def _acquire_pid_lock(self) -> None:
        """
        #91 — Escribe el PID del proceso actual en bot.pid.
        Si ya existe un bot.pid con un PID activo, termina con error.
        Previene el escenario de 5 instancias paralelas observado en prod.
        """
        import os
        self._PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        if self._PID_FILE.exists():
            try:
                old_pid = int(self._PID_FILE.read_text().strip())
                if _pid_still_running(old_pid):
                    logger.critical(
                        f"#91 PID LOCK: ya hay una instancia corriendo (PID={old_pid}). "
                        f"Terminando este proceso para evitar duplicados."
                    )
                    sys.exit(2)
            except (ValueError, OSError):
                pass
        self._PID_FILE.write_text(str(os.getpid()))
        logger.info(f"#91 PID lock adquirido: {os.getpid()} → {self._PID_FILE}")

    def _release_pid_lock(self) -> None:
        """Libera el PID lock al terminar."""
        try:
            if self._PID_FILE.exists():
                stored = int(self._PID_FILE.read_text().strip())
                if stored == os.getpid():
                    self._PID_FILE.unlink()
                    logger.info(f"#91 PID lock liberado")
        except Exception:
            pass

    def start(self) -> None:
        """Loop principal — corre indefinidamente hasta Ctrl+C."""
        # #91 — Prevenir instancias paralelas
        self._acquire_pid_lock()

        if not self.connector.connect():
            logger.error("No se pudo conectar a MT5. Abortando.")
            self._release_pid_lock()
            sys.exit(1)

        # Inicializar portfolio desde balance real — evita kill switch por mismatch
        self._init_portfolio_from_mt5()

        # #44 — Recuperar estado previo si el bot se reinició hoy
        self._load_state()

        # #83 — SL Recovery: proteger posiciones abiertas sin SL tras un reinicio
        if not self.dry_run:
            self._recover_missing_sl()

        # ── Verificar AutoTrading ─────────────────────────────────────────────
        if not self.dry_run:
            at_enabled = self.connector.check_autotrading()
            if at_enabled:
                logger.info("✅ AutoTrading: HABILITADO — órdenes se ejecutarán normalmente")
            else:
                logger.critical("🚨 AutoTrading: DESACTIVADO en MT5")
                logger.critical("   → Habilitar: toolbar MT5 → botón 'Algo Trading' (debe quedar VERDE)")
                logger.critical("   → Sin esto, todas las órdenes serán rechazadas (retcode=10027)")
                tg.info("⚠️ AutoTrading DESACTIVADO — habilitar en MT5 para que operen las órdenes")

        is_live = settings.mode == "live"
        mode_label = "🔴 LIVE (cuenta real)" if is_live else ("📋 DRY RUN" if self.dry_run else "🟡 DEMO (simulado)")

        logger.info("=" * 65)
        logger.info("  MQ26 BOT v2 — LIVE TRADING ACTIVO  [S03 v4]" if is_live else "  MQ26 BOT v2 — DEMO TRADING  [S03 v4]")
        logger.info(f"  Modo:      {mode_label}")
        logger.info(f"  Cuenta:    #{settings.mt5.login} | ${self.portfolio.equity:,.2f}")
        logger.info(f"  Símbolos:  {self.symbols}")
        logger.info(f"  Risk/trade: {settings.risk.risk_per_trade_pct}% (${self.portfolio.equity * settings.risk.risk_per_trade_pct / 100:.2f})")
        logger.info(f"  Kill switch: {settings.risk.dd_kill_switch_pct}% (${self.portfolio.equity * settings.risk.dd_kill_switch_pct / 100:.2f} máx pérdida)")
        logger.info(f"  Intervalo: {LOOP_INTERVAL_SEC}s | Max pos: {MAX_OPEN_POSITIONS}")
        logger.info("=" * 65)

        try:
            while True:
                self._tick()
                logger.info(f"Próxima evaluación en {LOOP_INTERVAL_SEC}s — Ctrl+C para detener")
                time.sleep(LOOP_INTERVAL_SEC)

        except KeyboardInterrupt:
            logger.info("Loop detenido por el usuario.")
        finally:
            self._print_session_summary()
            self.connector.disconnect()
            self._release_pid_lock()   # #91

    # ─── Tick principal ───────────────────────────────────────────────────────

    def _tick(self) -> None:
        """Una iteración del loop."""
        now = datetime.now(timezone.utc)
        logger.info(f"--- Tick {now.strftime('%Y-%m-%d %H:%M:%S')} UTC ---")

        # Reset diario
        today_str = now.strftime("%Y-%m-%d")
        if today_str != self._last_date:
            # #61/#67 — Guardar resumen del día anterior y enviar reporte Telegram
            try:
                trade_journal.update_daily_summary(
                    equity_close=self.portfolio.equity,
                    max_dd_pct=self.portfolio.drawdown_pct,
                )
                today_stats = trade_journal.get_today_stats()
                weekly      = trade_journal.get_weekly_stats()

                if weekly.get("total_trades", 0) > 0:
                    logger.info(
                        f"#61 Semana | Trades={weekly['total_trades']} "
                        f"WR={weekly.get('win_rate', 0):.0%} "
                        f"PnL=${weekly.get('total_pnl_usd', 0):+.2f} "
                        f"AvgRR={weekly.get('avg_rr', 0):.2f}"
                    )

                # #67 — Telegram daily report con estadísticas completas
                pnl_usd = today_stats.get("pnl_usd", 0.0)
                pnl_pct = (pnl_usd / max(self._equity_at_day_open, 1)) * 100
                tg.daily_report(
                    date=self._last_date,
                    trades=today_stats.get("trades", 0),
                    pnl_usd=pnl_usd,
                    pnl_pct=pnl_pct,
                    win_rate=today_stats.get("win_rate", 0.0),
                    equity=self.portfolio.equity,
                    dd_pct=self.portfolio.drawdown_pct,
                    weekly_stats=weekly,
                    by_symbol=weekly.get("by_symbol"),
                )
            except Exception as _je:
                logger.debug(f"journal/daily report error: {_je}")

            self._traded_today.clear()
            self._last_date = today_str
            self._daily_paused       = False
            self._daily_warned       = False    # #76 resetear advertencia diaria
            self._daily_hard_stopped = False    # #76 resetear stop total
            self._friday_closed_today = False   # #59 reiniciar bandera viernes
            acc = self.connector.get_account_info()
            self._equity_at_day_open = acc["equity"] if acc else self._equity_at_day_open
            logger.info(f"Reset diario | Equity apertura: ${self._equity_at_day_open:.2f}")
            log_today_schedule(now)   # M91 — mostrar eventos del día en log

        # Actualizar equity desde MT5
        self._update_equity()

        # #44 — Guardar estado en cada tick
        self._save_state()

        # #52/#53 — Gestionar posiciones abiertas (trailing SL BE + partial TP1)
        self._manage_positions()

        # #68 — Position Heat Monitor (alertas de floating P&L extremo)
        self._heat_monitor()

        # #59 — Cierre automático de posiciones FX el viernes antes del fin de semana
        self._check_friday_close(now)

        # #24 — Actualizar correlación dinámica (cada 6h)
        self._update_dynamic_correlation()

        # #85 — Re-rankear símbolos por P&L real del journal (semanal)
        self._update_symbol_ranking()

        # #90 — Verificar P&L semanal y ajustar weekly_scale (cada 4h)
        self._update_weekly_scale()

        # #47 — Heartbeat Telegram cada 6 horas
        import time as _time
        now_ts = _time.time()
        if now_ts - self._last_heartbeat >= 6 * 3600:
            open_pos = self.connector.get_open_positions()
            tg.heartbeat(
                equity=self.portfolio.equity if self.portfolio else 0,
                positions=len(open_pos),
                dd_pct=self.portfolio.drawdown_pct if self.portfolio else 0,
            )
            self._last_heartbeat = now_ts

        # M73 — Daily loss limit
        if self._daily_paused:
            logger.warning("DAILY LOSS LIMIT activo — sin nuevas entradas hoy")
            self._log_open_positions()
            return

        # #15 — Consecutive losses pause
        if self._consec_pause_until > now_ts:
            remaining_h = (self._consec_pause_until - now_ts) / 3600
            logger.warning(
                f"M15 CONSECUTIVE LOSSES ({self._consecutive_losses} seguidas) — "
                f"pausa activa, reanuda en {remaining_h:.1f}h"
            )
            self._log_open_positions()
            return

        # #76 — Tiered Daily Loss Limit
        daily_loss_pct = (self._equity_at_day_open - self.portfolio.equity) / max(self._equity_at_day_open, 1)

        if daily_loss_pct >= DAILY_LOSS_STOP:
            # Nivel 3: cerrar todo y detener
            if not getattr(self, "_daily_hard_stopped", False):
                self._daily_hard_stopped = True
                logger.critical(
                    f"#76 DAILY STOP {daily_loss_pct:.1%} ≥ {DAILY_LOSS_STOP:.0%} — "
                    f"cerrando posiciones y deteniendo entradas"
                )
                tg.info(
                    f"🛑 DAILY STOP: pérdida {daily_loss_pct:.1%} — "
                    f"cerrando posiciones abiertas"
                )
                for p in self.connector.get_open_positions():
                    self.connector.close_position(p["ticket"])
            self._daily_paused = True
            self._log_open_positions()
            return

        elif daily_loss_pct >= DAILY_LOSS_LIMIT:
            # Nivel 2: pausar nuevas entradas
            if not self._daily_paused:
                self._daily_paused = True
                logger.warning(
                    f"M73/#76 DAILY LOSS LIMIT: {daily_loss_pct:.1%} ≥ {DAILY_LOSS_LIMIT:.0%} — "
                    f"pausando nuevas entradas"
                )
                tg.info(f"⚠️ Daily loss {daily_loss_pct:.1%} — pausado hasta mañana")
            self._log_open_positions()
            return

        elif daily_loss_pct >= DAILY_LOSS_WARN:
            # Nivel 1: advertencia, size reducido al 50% (handled via _daily_warned flag)
            if not getattr(self, "_daily_warned", False):
                self._daily_warned = True
                logger.warning(
                    f"#76 DAILY WARNING: {daily_loss_pct:.1%} ≥ {DAILY_LOSS_WARN:.0%} — "
                    f"size reducido al 50%"
                )
                tg.info(f"⚠️ Daily P&L = {-daily_loss_pct:.1%} — size al 50% como precaución")
        else:
            # Pérdida dentro de límites normales — resetear advertencia si recuperó
            if getattr(self, "_daily_warned", False) and daily_loss_pct < DAILY_LOSS_WARN * 0.5:
                self._daily_warned = False
            if getattr(self, "_daily_hard_stopped", False) and daily_loss_pct < DAILY_LOSS_STOP * 0.5:
                self._daily_hard_stopped = False

        # Kill switch global
        if self.portfolio.drawdown_pct >= settings.risk.dd_kill_switch_pct:
            logger.critical(
                f"KILL SWITCH: DD={self.portfolio.drawdown_pct:.1f}% — cerrando todas las posiciones"
            )
            tg.kill_switch(self.portfolio.drawdown_pct, self.portfolio.equity)
            self.connector.kill_switch()
            return

        # M91 — Filtro de calendario económico
        in_blackout, blackout_reason = is_news_blackout(now=now)
        if in_blackout:
            logger.warning(f"M91 BLACKOUT: {blackout_reason} — sin nuevas entradas")
            self._log_open_positions()
            return

        # M77 — Máximo posiciones simultáneas
        open_positions = self.connector.get_open_positions()
        if len(open_positions) >= MAX_OPEN_POSITIONS:
            logger.info(f"M77: {len(open_positions)} posiciones abiertas — máximo {MAX_OPEN_POSITIONS} alcanzado")
            self._log_open_positions()
            return

        # M136 — Ordenar símbolos por Sharpe histórico (mayor primero)
        symbols_ranked = sorted(
            self.symbols,
            key=lambda s: SHARPE_RANK.get(s, 0),
            reverse=True,
        )

        # M72 — Rastrear qué grupos de correlación ya tienen señal este tick
        corr_groups_used: set[int] = set()

        # Evaluar cada símbolo en orden de prioridad
        slots_available = MAX_OPEN_POSITIONS - len(open_positions)

        for symbol in symbols_ranked:
            if slots_available <= 0:
                break

            if not is_market_open(symbol, now):
                logger.debug(f"{symbol}: mercado cerrado — omitiendo")
                continue

            # M72 — Verificar grupo de correlación
            corr_group_idx = self._get_corr_group(symbol)
            if corr_group_idx is not None and corr_group_idx in corr_groups_used:
                logger.debug(f"M72: {symbol} — grupo de correlación ya tiene señal activa, omitiendo")
                continue

            try:
                executed = self._evaluate_symbol(symbol, now)
                if executed:
                    slots_available -= 1
                    if corr_group_idx is not None:
                        corr_groups_used.add(corr_group_idx)
            except Exception as e:
                logger.error(f"Error evaluando {symbol}: {e}", exc_info=True)

        self._write_funnel_snapshot()
        self._log_open_positions()

    # ─── Evaluación por símbolo ───────────────────────────────────────────────

    def _evaluate_symbol(self, symbol: str, now: datetime) -> bool:
        """
        Descarga datos, genera señales y opera si corresponde.
        Returns True si se ejecutó una orden.
        """
        import time as _time_mod

        # ── #86 — Session Time Guard ─────────────────────────────────────────
        # S03 genera señales en 3 ventanas:
        #   · Asian scalp    (01:00–06:30 UTC)
        #   · London BO      (07:00–08:30 UTC)
        #   · NY Open BO     (12:00–14:00 UTC)  ← #95 nuevo modo
        # Ventana de evaluación: 23:00–14:59 UTC (cubre las 3 sesiones)
        hour_utc = now.hour
        is_evaluation_window = (hour_utc < 15) or (hour_utc >= 23)   # 23:00–14:59 UTC
        if symbol not in CRYPTO_SYMBOLS and not is_evaluation_window:
            logger.debug(
                f"#86 {symbol}: fuera de ventana de evaluación ({hour_utc:02d}:00 UTC) — skip"
            )
            self._signal_funnel["filtered_session"] += 1
            return False

        # ── #88 — Anti-Tilt Short Cooldown ──────────────────────────────────
        # Después de 2 pérdidas en < 2h → pausa 1h (adicional al 3-pérdidas → 24h)
        now_ts_tilt = _time_mod.time()
        if now_ts_tilt < getattr(self, "_tilt_cooldown_until", 0.0):
            remaining_m = (self._tilt_cooldown_until - now_ts_tilt) / 60
            logger.info(f"#88 Anti-tilt cooldown activo — reanuda en {remaining_m:.0f} min")
            return False

        # #72 — Auto-Blacklist: skip si símbolo pausado por pérdidas consecutivas
        sym_state = self._symbol_losses.get(symbol, {"losses": 0, "paused_until": 0.0})
        if sym_state["paused_until"] > _time_mod.time():
            remaining_h = (sym_state["paused_until"] - _time_mod.time()) / 3600
            logger.info(f"#72 {symbol}: pausado por pérdidas (reanuda en {remaining_h:.1f}h)")
            return False

        # #7 — Spread check estático inicial (umbrales calibrados en mt5_connector._MAX_SPREAD)
        spread_ok, spread_val = self.connector.check_spread(symbol)
        if not spread_ok:
            logger.warning(f"#7 Spread excesivo en {symbol}: {spread_val:.1f} pips — señal descartada")
            self._signal_funnel["filtered_spread"] += 1
            return False

        # 1. Datos frescos de MT5
        df_m5 = self.connector.get_ohlcv(symbol, TIMEFRAME_SIGNAL,  BARS_SIGNAL)
        df_h1 = self.connector.get_ohlcv(symbol, TIMEFRAME_CONTEXT, BARS_CONTEXT)

        if df_m5.empty or df_h1.empty:
            logger.warning(f"{symbol}: sin datos OHLCV")
            return False

        # 2. Indicadores
        from core.market_structure import add_indicators
        df_m5 = add_indicators(df_m5)
        df_h1 = add_indicators(df_h1)

        # #64 — Dynamic Spread Threshold: segunda verificación con ATR como referencia
        try:
            instr = INSTRUMENTS.get(symbol)
            if instr and "atr" in df_m5.columns:
                atr_val  = df_m5["atr"].iloc[-1]
                atr_pips = atr_val / instr.pip_size
                spread_ok_dyn, spread_now = self.connector.check_spread(symbol, atr_pips=atr_pips)
                if not spread_ok_dyn:
                    logger.warning(
                        f"#64 Spread excesivo en {symbol}: {spread_now:.1f} pips "
                        f"(dyn max={max(self.connector._MAX_SPREAD.get(symbol, 10), atr_pips*0.15):.1f}) — skip"
                    )
                    self._signal_funnel["filtered_spread"] += 1
                    return False
        except Exception as _se:
            logger.debug(f"#64 spread dynamic check error {symbol}: {_se}")

        # ── #55 H4 Macro Trend Filter ─────────────────────────────────────────
        # Ajusta la confianza de señales counter-trend al sesgo H4
        h4_bias = "NEUTRAL"
        try:
            df_h4 = self.connector.get_ohlcv(symbol, "H4", BARS_H4)
            if not df_h4.empty and len(df_h4) >= 50:
                df_h4   = add_indicators(df_h4)
                ema50_h4 = df_h4["ema_50"].iloc[-1] if "ema_50" in df_h4.columns else float("nan")
                close_h4 = df_h4["close"].iloc[-1]
                if not pd.isna(ema50_h4):
                    h4_bias = "BULL" if close_h4 > ema50_h4 else "BEAR"
                    logger.debug(f"#55 {symbol}: H4 bias={h4_bias} (close={close_h4:.5f} vs EMA50={ema50_h4:.5f})")
        except Exception as _h4e:
            logger.debug(f"#55 H4 filter error {symbol}: {_h4e}")

        # 3. Señales
        signals = self.strategy.generate_signals(df_m5, df_h1, symbol)

        # ── #55 Aplicar sesgo H4: reducir confidence de señales counter-trend ──
        if h4_bias != "NEUTRAL" and signals:
            from strategies.base import SignalDirection
            for sig in signals:
                is_counter = (h4_bias == "BULL" and sig.direction == SignalDirection.SHORT) or \
                             (h4_bias == "BEAR" and sig.direction == SignalDirection.LONG)
                if is_counter:
                    sig.confidence = max(0.3, sig.confidence * 0.5)
                    logger.info(
                        f"#55 {symbol}: señal {sig.direction.name} counter-trend vs H4 ({h4_bias}) "
                        f"→ confidence reducida a {sig.confidence:.0%}"
                    )

        if not signals:
            logger.debug(f"{symbol}: sin señales en este tick")
            return False

        self._signal_funnel["generated"] += len(signals)

        # Señal más reciente
        latest = max(signals, key=lambda s: s.timestamp)

        # ── #70 Minimum R:R Filter ────────────────────────────────────────────
        MIN_RR = 1.5
        if latest.r_r_ratio < MIN_RR:
            logger.info(
                f"#70 {symbol}: R:R={latest.r_r_ratio:.2f} < {MIN_RR} mínimo — señal descartada"
            )
            return False

        # ── Evitar duplicados — key estable por dirección (no por minuto de barra) ──
        # Bug anterior: key incluía HH:MM del bar M5 → misma señal se re-intentaba
        # cada 5 min con una key nueva. Ahora: una sola operación por dirección por sesión por día.
        # Para señales NY Open BO se usa sufijo _NY, permitiendo que coexistan con
        # señales de la misma dirección de la sesión Asian/London del mismo día.
        today_str_key = now.strftime("%Y%m%d")
        signal_mode   = "_NY" if "NY Open" in (latest.notes or "") else ""
        sig_key = f"{symbol}_{today_str_key}_{latest.direction.name}{signal_mode}"
        if sig_key in self._traded_today:
            logger.debug(f"{symbol}: señal {latest.direction.name}{signal_mode} de hoy ya procesada ({sig_key})")
            return False

        # ── #51 Staleness filter: descartar señales > 2 horas de antigüedad ──
        try:
            sig_ts = latest.timestamp
            if hasattr(sig_ts, 'tzinfo') and sig_ts.tzinfo is None:
                sig_ts = sig_ts.tz_localize("UTC")
            now_pd = pd.Timestamp(now)
            signal_age_h = (now_pd - sig_ts).total_seconds() / 3600
            if signal_age_h > MAX_SIGNAL_AGE_H:
                logger.info(
                    f"#51 {symbol}: señal de hace {signal_age_h:.1f}h — antigua, descartando"
                )
                self._signal_funnel["filtered_staleness"] += 1
                self._traded_today.add(sig_key)
                return False
        except Exception as _age_err:
            logger.debug(f"Staleness check error: {_age_err}")

        # ── #78 Price-TP Staleness: señal ya cumplida (precio pasó el TP) ────
        # Si el precio actual ya superó el TP1, la señal es irrelevante (el movimiento ya ocurrió)
        try:
            tick_now = self.connector.get_tick(symbol)
            if tick_now:
                from strategies.base import SignalDirection
                mid_price = (tick_now["bid"] + tick_now["ask"]) / 2
                tp_breached = (
                    (latest.direction == SignalDirection.LONG  and mid_price >= latest.tp1_price) or
                    (latest.direction == SignalDirection.SHORT and mid_price <= latest.tp1_price)
                )
                if tp_breached:
                    logger.info(
                        f"#78 {symbol}: precio actual {mid_price:.5f} ya pasó TP1 "
                        f"{latest.tp1_price:.5f} — señal ya cumplida, descartando"
                    )
                    self._traded_today.add(sig_key)
                    return False
        except Exception as _tp_err:
            logger.debug(f"#78 TP staleness check error: {_tp_err}")

        # ── #69 Multi-Timeframe Entry Confirmation ────────────────────────────
        # Verificar que la vela M15 actual esté a favor de la dirección
        try:
            df_m15 = self.connector.get_ohlcv(symbol, "M15", 3)
            if not df_m15.empty:
                last_m15 = df_m15.iloc[-1]
                body_pct = abs(last_m15["close"] - last_m15["open"]) / max(
                    abs(last_m15["high"] - last_m15["low"]), 1e-10
                )
                m15_bull = last_m15["close"] > last_m15["open"]
                m15_bear = last_m15["close"] < last_m15["open"]
                from strategies.base import SignalDirection
                mtf_ok = (
                    (latest.direction == SignalDirection.LONG  and (m15_bull or body_pct < 0.20)) or
                    (latest.direction == SignalDirection.SHORT and (m15_bear or body_pct < 0.20))
                )
                if not mtf_ok:
                    logger.info(
                        f"#69 MTF reject {symbol}: M15 contra la señal "
                        f"({'alcista' if m15_bull else 'bajista'} vs {latest.direction.name})"
                    )
                    return False
        except Exception as _m15e:
            logger.debug(f"#69 MTF check error: {_m15e}")

        asset_cls = INSTRUMENTS[symbol].asset_class if symbol in INSTRUMENTS else "?"
        logger.info(
            f"SEÑAL {latest.direction.name} | {symbol} [{asset_cls}] | "
            f"Entry={latest.entry_price:.5f} SL={latest.sl_price:.5f} "
            f"TP1={latest.tp1_price:.5f} TP2={latest.tp2_price:.5f} | "
            f"R:R={latest.r_r_ratio:.2f} | {latest.notes}"
        )
        tg.signal_detected(
            symbol=symbol, direction=latest.direction.name,
            entry=latest.entry_price, sl=latest.sl_price,
            tp1=latest.tp1_price, tp2=latest.tp2_price,
            rr=latest.r_r_ratio, notes=latest.notes,
        )

        # 4. Tamaño de posición
        instrument = INSTRUMENTS.get(symbol)
        if instrument is None:
            logger.warning(f"Instrumento {symbol} no en config/instruments.py")
            return False

        # #24 — Correlación dinámica (reemplaza grupos estáticos M72)
        corr_reduction = self._get_dynamic_corr_reduction(symbol)

        # #71 — Equity regime: reducir confidence 20% en modo bearish
        if getattr(self, "_equity_regime", "normal") == "bearish":
            old_conf = latest.confidence
            latest.confidence = max(0.25, latest.confidence * 0.80)
            if latest.confidence < old_conf:
                logger.debug(
                    f"#71 {symbol}: confidence reducida {old_conf:.0%} → {latest.confidence:.0%} (equity bearish)"
                )

        if self.sizer is None:
            logger.error("Sizer no inicializado — llamar start() primero")
            return False

        sizing = self.sizer.calculate_size(latest, instrument, now)
        if not sizing.approved:
            logger.warning(f"{symbol}: señal rechazada por riesgo — {sizing.rejection_reason}")
            return False

        # #76 — Nivel 1: size reducido al 50% cuando hay daily warning activa
        warn_mult = 0.50 if getattr(self, "_daily_warned", False) else 1.0

        # #84 — Consecutive Win Scaling: tras ≥3 wins, escalar size hasta ×2.0
        # 3 wins → ×1.25 | 4 wins → ×1.50 | 5 wins → ×1.75 | 6+ wins → ×2.0 (duplicar)
        wins_now  = getattr(self, "_consecutive_wins", 0)
        win_scale = min(2.0, 1.0 + max(0, wins_now - 2) * 0.25) if wins_now >= 3 else 1.0

        weekly_sc = getattr(self, "_weekly_scale", 1.0)   # #90 protección semanal

        lot_adjusted = round(
            sizing.lot_size * corr_reduction * warn_mult * win_scale * weekly_sc
            / instrument.lot_step
        ) * instrument.lot_step
        lot_adjusted  = max(instrument.min_lot, lot_adjusted)

        if corr_reduction < 1.0:
            logger.info(f"M72 Correlación: {symbol} size reducido {corr_reduction:.0%} → {lot_adjusted:.2f} lot")
        if warn_mult < 1.0:
            logger.info(f"#76 Daily warning: {symbol} size reducido al 50% → {lot_adjusted:.2f} lot")
        if win_scale > 1.0:
            logger.info(f"#84 Win scale ×{win_scale:.2f} ({wins_now} wins consecutivos) → {lot_adjusted:.2f} lot")
        if weekly_sc < 1.0:
            logger.info(f"#90 Weekly scale ×{weekly_sc:.0%} (protección semanal) → {lot_adjusted:.2f} lot")

        logger.info(
            f"Tamaño aprobado | {symbol} | Lot={lot_adjusted:.2f} | "
            f"Riesgo≈${sizing.risk_usd * corr_reduction:.2f} ({sizing.risk_pct * corr_reduction:.2f}%)"
        )

        # 5. Enviar orden
        self._traded_today.add(sig_key)

        if self.dry_run:
            logger.info(f"[DRY RUN] Orden simulada: {latest.direction.name} {lot_adjusted:.2f} {symbol}")
            self._signal_funnel["executed"] += 1
            return True

        # #74 — Volatility-Adjusted SL: verificar que el SL tenga al menos 1× ATR de distancia
        # Si el SL calculado por la estrategia es menor que ATR, expandirlo para evitar ruido
        try:
            if "atr" in df_m5.columns:
                atr_now = df_m5["atr"].iloc[-1]
                instr   = INSTRUMENTS.get(symbol)
                if instr and atr_now > 0:
                    sl_dist_price = abs(latest.entry_price - latest.sl_price)
                    if sl_dist_price < atr_now * 0.8:  # SL < 0.8× ATR → muy expuesto al ruido
                        direction_ = latest.direction.name
                        if direction_ == "LONG":
                            latest.sl_price = latest.entry_price - atr_now * 1.0
                        else:
                            latest.sl_price = latest.entry_price + atr_now * 1.0
                        logger.info(
                            f"#74 {symbol}: SL ajustado por ATR | "
                            f"original dist={sl_dist_price:.5f} → nuevo SL={latest.sl_price:.5f} (ATR={atr_now:.5f})"
                        )
        except Exception as _e74:
            logger.debug(f"#74 volatility SL adjust error: {_e74}")

        # #73 — Smart Limit Entry: intentar limit order si entry_price difiere del mercado actual
        result = None
        try:
            lmt_result = self.connector.send_limit_order(
                symbol      = symbol,
                direction   = latest.direction.name,
                lot_size    = lot_adjusted,
                entry_price = latest.entry_price,
                sl_price    = latest.sl_price,
                tp1_price   = latest.tp1_price,
                expiry_hours = 2.0,
            )
            if lmt_result:
                result = lmt_result
                logger.info(f"#73 Limit order colocada para {symbol} — esperando fill")
        except Exception as _le:
            logger.debug(f"#73 Limit order error {symbol}: {_le}")

        # Fallback a market order si limit no aplica o falla
        if result is None:
            result = self.connector.send_market_order(
                symbol    = symbol,
                direction = latest.direction.name,
                lot_size  = lot_adjusted,
                sl_price  = latest.sl_price,
                tp1_price = latest.tp1_price,
                tp2_price = latest.tp2_price,
            )

        if result:
            self.sizer.record_trade_open(latest)
            # #38 — Registrar en trade journal
            trade_journal.record_open(
                ticket=result["ticket"], symbol=symbol,
                direction=result["direction"], lot=result["lot"],
                entry_price=result["price"], sl_price=latest.sl_price,
                tp1_price=latest.tp1_price, notes=latest.notes,
            )
            # #52/#53 — Registrar en position manager para trailing SL y partial TP1
            self._managed_positions[result["ticket"]] = {
                "symbol":    symbol,
                "direction": result["direction"],
                "entry":     result["price"],
                "sl_orig":   latest.sl_price,
                "tp1":       latest.tp1_price,
                "tp2":       latest.tp2_price,
                "lot":       result["lot"],
                "risk":      abs(result["price"] - latest.sl_price),
                "be_done":   False,   # SL todavía no movido a BE
                "tp1_done":  False,   # cierre parcial TP1 no hecho aún
            }
            logger.info(
                f"ORDEN EJECUTADA | Ticket={result['ticket']} | "
                f"{result['direction']} {result['lot']} {symbol} @ {result['price']:.5f}"
            )
            tg.order_executed(
                symbol=symbol, direction=result["direction"],
                lot=result["lot"], price=result["price"],
                ticket=result["ticket"],
                risk_usd=sizing.risk_usd * corr_reduction,
            )
            self._signal_funnel["executed"] += 1
            return True
        else:
            logger.error(f"Orden fallida para {symbol}")
            return False

    # ─── #44 State Persistence ───────────────────────────────────────────────

    def _save_state(self) -> None:
        """Persiste el estado crítico del bot a JSON para recuperación tras crash."""
        state = {
            "consecutive_losses": self._consecutive_losses,
            "consec_pause_until": self._consec_pause_until,
            "daily_paused":       self._daily_paused,
            "equity_at_day_open": self._equity_at_day_open,
            "last_date":          self._last_date,
            "traded_today":       list(self._traded_today),
            "saved_at":           datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                __import__("json").dumps(state, indent=2)
            )
        except Exception as e:
            logger.debug(f"State save error: {e}")

    def _load_state(self) -> None:
        """Recupera estado previo si existe y es de hoy."""
        try:
            if not self._state_file.exists():
                return
            state = __import__("json").loads(self._state_file.read_text())
            saved_date = state.get("last_date", "")
            today_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if saved_date != today_str:
                return   # estado de otro día, ignorar

            self._consecutive_losses  = state.get("consecutive_losses", 0)
            self._consec_pause_until  = state.get("consec_pause_until", 0.0)
            self._daily_paused        = state.get("daily_paused", False)
            self._equity_at_day_open  = state.get("equity_at_day_open", self._equity_at_day_open)
            self._last_date           = saved_date
            self._traded_today        = set(state.get("traded_today", []))
            logger.info(
                f"#44 Estado recuperado desde {self._state_file.name} | "
                f"Señales ya operadas hoy: {len(self._traded_today)}"
            )
        except Exception as e:
            logger.debug(f"State load error: {e}")

    # ─── #24 Correlación Dinámica ────────────────────────────────────────────

    def _update_dynamic_correlation(self) -> None:
        """Recalcula la matriz de correlación rolling 20d cada 6 horas."""
        now_ts = time.time()
        if now_ts - self._corr_last_update < 6 * 3600:
            return

        try:
            import numpy as np
            prices: dict[str, list[float]] = {}
            for sym in self.symbols:
                df = self.connector.get_ohlcv(sym, "H1", 480)  # 20d × 24h
                if not df.empty:
                    prices[sym] = df["close"].tolist()[-480:]

            if len(prices) < 2:
                return

            # Calcular matriz de correlación
            min_len = min(len(v) for v in prices.values())
            syms = list(prices.keys())
            matrix: dict[str, dict[str, float]] = {}

            for i, s1 in enumerate(syms):
                matrix[s1] = {}
                for s2 in syms:
                    if s1 == s2:
                        matrix[s1][s2] = 1.0
                        continue
                    v1 = prices[s1][-min_len:]
                    v2 = prices[s2][-min_len:]
                    try:
                        corr = float(np.corrcoef(v1, v2)[0, 1])
                    except Exception:
                        corr = 0.0
                    matrix[s1][s2] = corr

            self._corr_matrix = matrix
            self._corr_last_update = now_ts
            logger.info(
                f"#24 Correlación dinámica actualizada | "
                f"Pares: {list(matrix.keys())}"
            )
        except Exception as e:
            logger.debug(f"Dynamic correlation error: {e}")

    def _get_dynamic_corr_reduction(self, symbol: str) -> float:
        """#24 — Retorna factor de reducción de size basado en correlación real."""
        if not self._corr_matrix:
            # Fallback a grupos estáticos
            return 0.6 if self._is_corr_pair(symbol) else 1.0

        max_corr = max(
            (abs(self._corr_matrix.get(symbol, {}).get(other, 0.0))
             for other in self.symbols if other != symbol),
            default=0.0,
        )
        if max_corr > 0.85:
            return 0.5    # correlación muy alta → reducir al 50%
        if max_corr > 0.70:
            return 0.6    # correlación alta → reducir al 60% (igual que antes)
        if max_corr > 0.50:
            return 0.8    # correlación media → reducir al 80%
        return 1.0        # baja correlación → tamaño completo

    # ─── Consecutive losses tracker (#15) ────────────────────────────────────

    def record_trade_result(self, pnl_usd: float) -> None:
        """
        Registrar el resultado de un trade cerrado.
        Si hay N pérdidas consecutivas → pausar 24 horas.
        """
        import time as _time
        pause_after = settings.risk.consecutive_losses_pause  # default: 3

        if pnl_usd < 0:
            self._consecutive_losses += 1
            self._consecutive_wins = 0   # #84 reset racha ganadora
            logger.info(f"Pérdida registrada — consecutivas: {self._consecutive_losses}/{pause_after}")

            # #88 — Anti-Tilt: registrar timestamp de pérdida
            now_ts88 = _time.time()
            self._tilt_losses = [t for t in self._tilt_losses if now_ts88 - t < 7200]  # últimas 2h
            self._tilt_losses.append(now_ts88)
            if len(self._tilt_losses) >= 2:
                self._tilt_cooldown_until = now_ts88 + 3600  # 1h cooldown
                logger.warning(
                    f"#88 Anti-tilt: {len(self._tilt_losses)} pérdidas en 2h → "
                    f"cooldown 1h"
                )
                tg.info(f"⏸️ Anti-tilt activo — {len(self._tilt_losses)} pérdidas en 2h → pausa 1h")

            if self._consecutive_losses >= pause_after:
                self._consec_pause_until = _time.time() + 24 * 3600
                logger.warning(
                    f"#15 CONSECUTIVE LOSSES: {self._consecutive_losses} pérdidas seguidas — "
                    f"pausando 24 horas"
                )
                tg.info(
                    f"⚠️ {self._consecutive_losses} pérdidas consecutivas — "
                    f"bot pausado 24h para proteger capital"
                )
        else:
            # Trade ganador resetea el contador de pérdidas y sube el de wins
            if self._consecutive_losses > 0:
                logger.info(f"Trade ganador — reseteando contador de pérdidas (era {self._consecutive_losses})")
            self._consecutive_losses = 0
            self._consecutive_wins  += 1   # #84 incrementar racha ganadora
            if self._consecutive_wins >= 3:
                scale = min(2.0, 1.0 + (self._consecutive_wins - 2) * 0.25)
                logger.info(f"#84 Racha ganadora: {self._consecutive_wins} wins consecutivos → size ×{scale:.2f}")

    # ─── #90 Weekly P&L Scale Protection ────────────────────────────────────

    def _update_weekly_scale(self) -> None:
        """
        #90 — Si la semana tiene pérdidas > 3%, reducir el size de posiciones al 50%
        para proteger el capital restante. Se revisa cada 4 horas.

        Niveles:
          - weekly_pnl ≥ 0%        → scale = 1.0 (normal)
          - weekly_pnl ∈ [-3%, 0%] → scale = 0.75 (reducción moderada)
          - weekly_pnl < -3%       → scale = 0.50 (protección máxima)
        """
        import time as _t90
        now90 = _t90.time()
        if now90 - self._weekly_scale_last_check < 4 * 3600:
            return  # solo revisar cada 4 horas

        self._weekly_scale_last_check = now90
        try:
            weekly = trade_journal.get_weekly_stats()
            total_pnl  = weekly.get("total_pnl_usd", 0.0)
            base_equity = max(self.portfolio.peak_equity, 1) if self.portfolio else 1
            weekly_pct  = total_pnl / base_equity

            if weekly_pct < -0.03:        # pérdida semanal > 3%
                new_scale = 0.50
            elif weekly_pct < 0.0:         # pérdida semanal 0–3%
                new_scale = 0.75
            else:
                new_scale = 1.0            # semana positiva o plana

            if new_scale != self._weekly_scale:
                prev = self._weekly_scale
                self._weekly_scale = new_scale
                logger.warning(
                    f"#90 Weekly scale: {prev:.0%} → {new_scale:.0%} | "
                    f"PnL semana=${total_pnl:+.2f} ({weekly_pct:+.1%})"
                )
                if new_scale < 1.0:
                    tg.info(
                        f"📉 <b>Protección semanal activa</b>\n"
                        f"P&L semana: ${total_pnl:+.2f} ({weekly_pct:+.1%})\n"
                        f"Size reducido a {new_scale:.0%} hasta recuperar"
                    )
                else:
                    logger.info(f"#90 Weekly scale recuperado al 100%")
        except Exception as e:
            logger.debug(f"#90 weekly scale error: {e}")

    # ─── #85 Symbol Performance Auto-Ranking ────────────────────────────────

    def _update_symbol_ranking(self) -> None:
        """
        #85 — Re-rankear símbolos semanalmente basado en P&L real del journal
        (últimos 30 días). Actualiza el dict global SHARPE_RANK con Sharpe approx
        calculado como (avg_pnl / std_pnl) × sqrt(N_trades).
        Se ejecuta máximo una vez por semana (168 horas).
        """
        now_ts = time.time()
        if now_ts - self._sharpe_rank_last_update < 7 * 24 * 3600:
            return  # solo actualizar semanalmente

        updated = False
        try:
            import math
            for sym in self.symbols:
                stats = trade_journal.get_symbol_stats(sym, days=30)
                trades    = stats.get("trades", 0)
                if trades < 5:
                    continue  # insuficientes datos para ranking estadístico

                win_rate   = stats.get("win_rate", 0.5)
                avg_rr     = stats.get("avg_rr", 1.0)
                expectancy = stats.get("expectancy", 0.0)  # avg PnL por trade

                # Sharpe aproximado: WR × AvgRR × √(N) — proxy del rendimiento ajustado
                # Un símbolo con alta WR y buen AvgRR, escalado por muestra, sube en ranking
                sharpe_approx = win_rate * avg_rr * math.sqrt(trades)

                # Penalizar símbolos con expectancy negativa
                if expectancy < 0:
                    sharpe_approx = max(-5.0, sharpe_approx * -1.0)

                old_rank      = SHARPE_RANK.get(sym, 0.0)
                SHARPE_RANK[sym] = round(sharpe_approx, 2)
                updated = True
                logger.info(
                    f"#85 Ranking {sym}: {old_rank:.2f} → {sharpe_approx:.2f} "
                    f"({trades}t WR={win_rate:.0%} AvgRR={avg_rr:.2f} exp=${expectancy:.2f})"
                )

            if updated:
                top = sorted(SHARPE_RANK.items(), key=lambda x: -x[1])
                ranking_str = " | ".join(f"{s}({v:.1f})" for s, v in top[:5])
                logger.info(f"#85 Ranking actualizado: {ranking_str}")
                tg.info(f"📊 <b>Ranking semanal</b>\n{ranking_str}")

        except Exception as e:
            logger.debug(f"#85 Auto-ranking error: {e}")

        self._sharpe_rank_last_update = now_ts

    # ─── Correlación inter-pares (M72) ───────────────────────────────────────

    def _get_corr_group(self, symbol: str) -> int | None:
        """Retorna el índice del grupo de correlación del símbolo, o None."""
        for i, group in enumerate(CORR_GROUPS):
            if symbol in group:
                return i
        return None

    def _is_corr_pair(self, symbol: str) -> bool:
        """True si el símbolo pertenece a algún grupo de correlación."""
        return any(symbol in g for g in CORR_GROUPS)

    # ─── #52/#53 Position Manager — Trailing SL + Partial TP1 ───────────────

    def _manage_positions(self) -> None:
        """
        #52 Trailing Stop to Break-Even: cuando la posición gana ≥ 60% del riesgo
              inicial, mueve el SL al precio de entrada (break-even).
        #53 Partial TP1: cuando el precio cruza TP1, cierra el 50% y mueve SL a BE.

        Se ejecuta cada tick sobre todas las posiciones rastreadas.
        """
        if not self._managed_positions:
            return

        positions = self.connector.get_open_positions()
        open_tickets = {p["ticket"] for p in positions}
        open_by_ticket = {p["ticket"]: p for p in positions}

        # Eliminar posiciones ya cerradas del rastreador
        closed = set(self._managed_positions.keys()) - open_tickets
        for t in closed:
            self._managed_positions.pop(t, None)

        for ticket, meta in list(self._managed_positions.items()):
            if ticket not in open_by_ticket:
                continue

            pos       = open_by_ticket[ticket]
            symbol    = meta["symbol"]
            direction = meta["direction"]
            entry     = meta["entry"]
            risk      = meta["risk"]
            tp1       = meta["tp1"]
            tp2       = meta.get("tp2", 0.0)

            tick = self.connector.get_tick(symbol)
            if tick is None:
                continue

            current_price = tick["bid"] if direction == "BUY" else tick["ask"]

            # Profit actual en precio
            if direction == "BUY":
                profit_pts = current_price - entry
            else:
                profit_pts = entry - current_price

            # ── #52 Break-Even Stop ──────────────────────────────────────────
            if not meta["be_done"] and profit_pts >= risk * BE_TRIGGER_R:
                new_sl = entry  # mover SL exactamente al entry (break-even)
                # Ajustar por mínima distancia de stops
                sym_info = None
                try:
                    import MetaTrader5 as _mt5
                    sym_info = _mt5.symbol_info(symbol)
                except Exception:
                    pass
                if sym_info:
                    min_dist = sym_info.trade_stops_level * sym_info.point
                    if direction == "BUY":
                        new_sl = max(new_sl, current_price - min_dist * 2)
                    else:
                        new_sl = min(new_sl, current_price + min_dist * 2)

                ok = self.connector.modify_sl(ticket, new_sl, meta.get("tp2", pos["tp"]))
                if ok:
                    meta["be_done"] = True
                    logger.info(
                        f"#52 BE Stop | {symbol} ticket={ticket} | "
                        f"SL movido a {new_sl:.5f} (entry={entry:.5f}) | "
                        f"profit={profit_pts:.5f} ≥ {risk * BE_TRIGGER_R:.5f}"
                    )
                    tg.info(
                        f"📐 <b>Break-Even Stop</b> — {symbol}\n"
                        f"SL movido a entry ({new_sl:.5f})"
                    )

            # ── #53 Partial Close at TP1 ─────────────────────────────────────
            if not meta["tp1_done"] and tp1 > 0:
                tp1_breached = (direction == "BUY"  and current_price >= tp1) or \
                               (direction == "SELL" and current_price <= tp1)
                if tp1_breached:
                    result = self.connector.partial_close(ticket, close_pct=0.5)
                    if result:
                        meta["tp1_done"] = True
                        meta["be_done"]  = True  # también activar BE si no estaba
                        pnl_approx = profit_pts * (meta["lot"] * 0.5) * 10  # estimado
                        logger.info(
                            f"#53 Partial TP1 | {symbol} ticket={ticket} | "
                            f"50% cerrado en {current_price:.5f} (TP1={tp1:.5f})"
                        )
                        tg.info(
                            f"🎯 <b>TP1 Parcial</b> — {symbol}\n"
                            f"50% cerrado @ {current_price:.5f} | "
                            f"Resto en TP2 ({tp2:.5f})"
                        )
                        # Mover SL a entry si no se hizo ya
                        if not meta.get("be_done"):
                            self.connector.modify_sl(ticket, entry)

            # ── #87 — TP2 Proximity Alert (antes de que MT5 cierre automático) ──
            # Cuando el precio alcanza TP2, alertar y asegurarse que el SL
            # esté protegiendo las ganancias máximas.
            if meta.get("tp1_done") and tp2 and tp2 != 0 and not meta.get("tp2_alerted"):
                tp2_breached = (
                    (direction == "BUY"  and current_price >= tp2) or
                    (direction == "SELL" and current_price <= tp2)
                )
                if tp2_breached:
                    meta["tp2_alerted"] = True
                    logger.info(
                        f"#87 TP2 alcanzado | {symbol} #{ticket} | "
                        f"precio={current_price:.5f} TP2={tp2:.5f}"
                    )
                    tg.trade_closed(
                        symbol=symbol, direction=direction,
                        outcome="tp2", pnl_usd=profit_pts * meta["lot"] * 10,
                        pnl_pips=profit_pts / (INSTRUMENTS.get(symbol).pip_size if symbol in INSTRUMENTS else 0.0001),
                        duration_h=0,
                    )

            # ── #81 Trailing SL toward TP2 (después de TP1 hit) ─────────────
            # Una vez cerrada la mitad en TP1, ajustar el SL del resto con ATR
            # para capturar el movimiento hacia TP2 sin exposición al retroceso.
            if meta.get("tp1_done") and tp2 and tp2 != 0:
                try:
                    df_m5_t = self.connector.get_ohlcv(symbol, "M5", 20)
                    if not df_m5_t.empty:
                        from core.market_structure import add_indicators as _ai
                        if "atr_14" not in df_m5_t.columns:
                            df_m5_t = _ai(df_m5_t)
                        atr_t = df_m5_t["atr_14"].iloc[-1] if "atr_14" in df_m5_t.columns else 0
                        if atr_t > 0:
                            if direction == "BUY":
                                trail_sl = current_price - atr_t * 1.5
                                curr_sl  = pos.get("sl", 0.0)
                                # Solo mover el SL hacia arriba (nunca hacia atrás)
                                if trail_sl > curr_sl and trail_sl > entry:
                                    ok = self.connector.modify_sl(ticket, trail_sl, tp2)
                                    if ok:
                                        logger.debug(
                                            f"#81 Trail SL ↑ {symbol} #{ticket}: "
                                            f"{curr_sl:.5f} → {trail_sl:.5f} (ATR={atr_t:.5f})"
                                        )
                            else:  # SELL
                                trail_sl = current_price + atr_t * 1.5
                                curr_sl  = pos.get("sl", float("inf"))
                                # Solo mover el SL hacia abajo (nunca hacia atrás)
                                if trail_sl < curr_sl and trail_sl < entry:
                                    ok = self.connector.modify_sl(ticket, trail_sl, tp2)
                                    if ok:
                                        logger.debug(
                                            f"#81 Trail SL ↓ {symbol} #{ticket}: "
                                            f"{curr_sl:.5f} → {trail_sl:.5f} (ATR={atr_t:.5f})"
                                        )
                except Exception as _e81:
                    logger.debug(f"#81 Trail SL error {symbol}: {_e81}")

            # ── #94 Pyramiding — Añadir a ganador entre TP1 y TP2 ───────────
            # Tras el cierre parcial en TP1, si el precio sigue avanzando hacia TP2,
            # abrimos una segunda posición (50% del lot original) con SL en entry.
            # Solo una vez por trade principal (flag pyramid_done), sin superar MAX_OPEN_POSITIONS.
            if (meta.get("tp1_done")
                    and tp2 and tp2 != 0
                    and not meta.get("pyramid_done")
                    and not self.dry_run):
                try:
                    # Calcular qué % del camino TP1→TP2 ya recorrió el precio
                    tp1_tp2_dist = abs(tp2 - (meta.get("tp1") or entry))
                    if tp1_tp2_dist > 0:
                        tp1_ref = meta.get("tp1") or (entry + (tp2 - entry) * 0.5)
                        if direction == "BUY":
                            progress = (current_price - tp1_ref) / tp1_tp2_dist
                        else:
                            progress = (tp1_ref - current_price) / tp1_tp2_dist

                        # Activar cuando el precio está 20%–65% del camino hacia TP2
                        if 0.20 <= progress <= 0.65:
                            open_count = len(self.connector.get_open_positions() or [])
                            if open_count < MAX_OPEN_POSITIONS:
                                instrument = INSTRUMENTS.get(symbol)
                                if instrument:
                                    raw_lot   = meta["lot"] * 0.5
                                    pyr_lot   = max(
                                        instrument.min_lot,
                                        round(raw_lot / instrument.lot_step) * instrument.lot_step
                                    )
                                    pyr_sl    = entry   # SL en entry (break-even garantizado)

                                    pyr_result = self.connector.send_market_order(
                                        symbol    = symbol,
                                        direction = direction,
                                        lot_size  = pyr_lot,
                                        sl_price  = pyr_sl,
                                        tp1_price = 0.0,    # sin parcial en pirámide
                                        tp2_price = tp2,
                                    )
                                    if pyr_result:
                                        pyr_ticket = pyr_result.get("ticket", 0)
                                        meta["pyramid_done"] = True

                                        # Registrar la pirámide para gestión de posiciones
                                        self._managed_positions[pyr_ticket] = {
                                            "symbol":      symbol,
                                            "direction":   direction,
                                            "entry":       pyr_result["price"],
                                            "sl_orig":     pyr_sl,
                                            "tp1":         0.0,
                                            "tp2":         tp2,
                                            "lot":         pyr_lot,
                                            "risk":        abs(pyr_result["price"] - pyr_sl),
                                            "be_done":     True,   # ya en BE desde el inicio
                                            "tp1_done":    True,   # no hay TP1 parcial
                                            "is_pyramid":  True,   # marcado para diferenciarlo
                                        }
                                        logger.info(
                                            f"#94 Pyramid | {symbol} ticket={pyr_ticket} | "
                                            f"{direction} {pyr_lot:.2f} lot @ {pyr_result['price']:.5f} | "
                                            f"SL=entry({pyr_sl:.5f}) TP={tp2:.5f} | "
                                            f"progreso={progress:.0%}"
                                        )
                                        tg.info(
                                            f"🔺 <b>PYRAMID ENTRY</b> — {symbol}\n"
                                            f"Añadidos {pyr_lot:.2f} lot @ {pyr_result['price']:.5f}\n"
                                            f"SL=entry ({pyr_sl:.5f}) | TP={tp2:.5f}"
                                        )
                except Exception as _e94:
                    logger.debug(f"#94 Pyramid error {symbol}: {_e94}")

    # ─── #83 SL Recovery on Restart ─────────────────────────────────────────

    def _recover_missing_sl(self) -> None:
        """
        #83 — Al arrancar, revisa si hay posiciones abiertas sin Stop Loss
        y les agrega uno conservador (2× ATR desde el entry) para proteger el capital
        en caso de un reinicio tras crash o apertura manual.
        """
        try:
            positions = self.connector.get_open_positions()
            if not positions:
                return
            needs_sl = [p for p in positions if p.get("sl", 0.0) == 0.0]
            if not needs_sl:
                return

            logger.warning(f"#83 SL Recovery: {len(needs_sl)} posición(es) sin SL detectadas")

            for pos in needs_sl:
                symbol    = pos["symbol"]
                direction = pos["direction"]
                entry     = pos["open_price"]
                ticket    = pos["ticket"]

                # Obtener ATR para dimensionar el SL
                try:
                    df_m5r = self.connector.get_ohlcv(symbol, "M5", 30)
                    if df_m5r.empty:
                        continue
                    from core.market_structure import add_indicators as _ai83
                    df_m5r = _ai83(df_m5r)
                    atr_r  = df_m5r["atr_14"].iloc[-1] if "atr_14" in df_m5r.columns else 0.0
                except Exception:
                    atr_r = 0.0

                if atr_r <= 0:
                    # Fallback: 0.5% del precio de entrada
                    atr_r = entry * 0.005

                if direction == "BUY":
                    sl_price = entry - atr_r * 2.0
                else:
                    sl_price = entry + atr_r * 2.0

                ok = self.connector.modify_sl(ticket, sl_price)
                if ok:
                    logger.warning(
                        f"#83 SL añadido: {direction} {symbol} #{ticket} "
                        f"entry={entry:.5f} → SL={sl_price:.5f} (ATR={atr_r:.5f})"
                    )
                    tg.info(
                        f"🛡️ <b>SL Recovery</b> — {symbol}\n"
                        f"Ticket #{ticket} sin SL → SL asignado: {sl_price:.5f}"
                    )
                else:
                    logger.error(f"#83 No se pudo añadir SL a {symbol} #{ticket}")
        except Exception as e:
            logger.warning(f"#83 SL Recovery error: {e}")

    # ─── #68 Position Heat Monitor ──────────────────────────────────────────

    def _heat_monitor(self) -> None:
        """
        #68 — Position Heat Monitor: envía alertas Telegram cuando una posición
        alcanza umbrales de ganancia/pérdida flotante relevantes.

        Alertas:
          🔥 HOT: profit ≥ 2R (posición ganando fuerte — considerar proteger)
          ❄️ COLD: profit ≤ -80% del riesgo (cerca del SL — prepararse)
          ✅ RECOVERED: era COLD pero volvió a positivo

        Estado de heat por ticket se guarda en _heat_state dict.
        """
        if not hasattr(self, "_heat_state"):
            self._heat_state: dict[int, str] = {}

        positions = self.connector.get_open_positions()
        if not positions:
            self._heat_state.clear()
            return

        for pos in positions:
            ticket = pos["ticket"]
            meta   = self._managed_positions.get(ticket)
            if meta is None:
                continue

            risk = meta.get("risk", 0.0)
            if risk <= 0:
                continue

            # Profit actual en unidades de precio
            entry     = meta["entry"]
            direction = meta["direction"]
            tick      = self.connector.get_tick(meta["symbol"])
            if tick is None:
                continue
            current = tick["bid"] if direction == "BUY" else tick["ask"]
            profit_pts = (current - entry) if direction == "BUY" else (entry - current)
            r_ratio    = profit_pts / risk  # en múltiplos de R

            prev_heat = self._heat_state.get(ticket, "normal")

            if r_ratio >= 2.0 and prev_heat != "hot":
                self._heat_state[ticket] = "hot"
                tg.info(
                    f"🔥 <b>Position Hot</b> — {meta['symbol']}\n"
                    f"Ticket #{ticket} | P&amp;L flotante = +{r_ratio:.1f}R\n"
                    f"Considera proteger ganancias (TP2={meta.get('tp2', 0):.5f})"
                )
                logger.info(f"#68 HOT {meta['symbol']} #{ticket}: {r_ratio:.1f}R flotante")

            elif r_ratio <= -0.80 and prev_heat != "cold":
                self._heat_state[ticket] = "cold"
                tg.info(
                    f"❄️ <b>Position Cold</b> — {meta['symbol']}\n"
                    f"Ticket #{ticket} | P&amp;L flotante = {r_ratio:.1f}R\n"
                    f"Cerca del SL — no intervenir"
                )
                logger.info(f"#68 COLD {meta['symbol']} #{ticket}: {r_ratio:.1f}R flotante")

            elif r_ratio > -0.20 and prev_heat == "cold":
                self._heat_state[ticket] = "normal"
                logger.info(f"#68 RECOVERED {meta['symbol']} #{ticket}: volvió a {r_ratio:.1f}R")

    # ─── #59 Friday Auto-Close ───────────────────────────────────────────────

    def _check_friday_close(self, now: datetime) -> None:
        """
        #59 — Cierra automáticamente todas las posiciones FX (no-crypto)
        el viernes a las 20:00 UTC para evitar riesgo de gap del fin de semana.
        Solo ejecuta una vez por día (bandera _friday_closed_today).
        """
        if now.weekday() != 4:          # solo viernes
            return
        if now.hour < FRIDAY_CLOSE_UTC:  # antes de las 20:00 UTC
            return
        if self._friday_closed_today:    # ya se ejecutó hoy
            return

        positions = self.connector.get_open_positions()
        fx_pos    = [p for p in positions if p["symbol"] not in CRYPTO_SYMBOLS]

        if not fx_pos:
            self._friday_closed_today = True
            return

        logger.warning(
            f"#59 VIERNES AUTO-CLOSE: {now.hour}:00 UTC — "
            f"cerrando {len(fx_pos)} posición(es) FX antes del fin de semana"
        )
        tg.info(
            f"⏰ <b>Cierre automático viernes</b>\n"
            f"Cerrando {len(fx_pos)} posición(es) FX — gap prevention"
        )

        for p in fx_pos:
            if self.connector.close_position(p["ticket"]):
                logger.info(
                    f"#59 Cerrado: {p['direction']} {p['volume']} "
                    f"{p['symbol']} @ {p['open_price']} | PnL≈${p['profit']:.2f}"
                )

        self._friday_closed_today = True

    # ─── #60 Trade Close Detection ───────────────────────────────────────────

    def _detect_closed_positions(self, current_positions: list[dict]) -> None:
        """
        #60 — Detecta posiciones que se cerraron desde el último tick comparando
        tickets. Cuando una posición cierra: actualiza journal, envía Telegram,
        registra resultado en sizer y contador de losses consecutivos.
        """
        current_tickets = {p["ticket"] for p in current_positions}
        closed_tickets  = self._prev_tickets - current_tickets

        for ticket in closed_tickets:
            prev = self._prev_positions_map.get(ticket)
            if prev is None:
                continue

            symbol    = prev["symbol"]
            direction = prev["direction"]
            open_pnl  = prev["profit"]  # P&L flotante al último tick antes del cierre

            # Intentar obtener el deal real desde MT5 history (más preciso)
            pnl_real = open_pnl
            outcome  = "unknown"
            try:
                deals = self.connector.get_closed_deals(minutes_back=10)
                deal  = next((d for d in deals if d["ticket"] == ticket), None)
                if deal:
                    pnl_real = deal["profit"] + deal.get("swap", 0)
                    comment  = deal.get("comment", "")
                    if "tp" in comment.lower():
                        outcome = "tp1"
                    elif "sl" in comment.lower():
                        outcome = "sl"
                    else:
                        outcome = "manual"
            except Exception as _de:
                logger.debug(f"deal history error: {_de}")

            # Duración aproximada
            from datetime import timezone as _tz
            open_time = prev.get("open_time")
            duration_h = 0.0
            if open_time:
                duration_h = (datetime.now(_tz.utc) - open_time).total_seconds() / 3600

            # Pip P&L estimado (para Telegram)
            instr = INSTRUMENTS.get(symbol)
            pnl_pips = 0.0
            if instr and instr.pip_value_usd > 0 and prev["volume"] > 0:
                pnl_pips = pnl_real / (instr.pip_value_usd * prev["volume"])

            logger.info(
                f"#60 Posición cerrada | {symbol} ticket={ticket} | "
                f"PnL=${pnl_real:+.2f} ({pnl_pips:+.1f} pips) | "
                f"outcome={outcome} | duración={duration_h:.1f}h"
            )

            # Telegram
            tg.trade_closed(
                symbol=symbol, direction=direction,
                outcome=outcome, pnl_usd=pnl_real, pnl_pips=pnl_pips,
                duration_h=duration_h,
            )

            # Journal
            if self.portfolio:
                trade_journal.record_close(
                    ticket=ticket, close_price=0,   # precio real de MT5 no disponible aquí
                    pnl_usd=pnl_real, outcome=outcome,
                    equity_after=self.portfolio.equity,
                )

            # Sizer
            if self.sizer:
                rr = abs(pnl_pips / (abs(prev.get("open_price", 1) - prev.get("sl", prev.get("open_price", 1))) / (instr.pip_size if instr else 0.0001) + 0.001))
                self.sizer.record_trade_close(pnl_real, rr)

            # #72 — Actualizar contador de pérdidas por símbolo
            import time as _t72
            sym_st = self._symbol_losses.setdefault(symbol, {"losses": 0, "paused_until": 0.0})
            if pnl_real < 0:
                sym_st["losses"] += 1
                BLACKLIST_LOSSES = 3    # N pérdidas consecutivas → pausa 24h
                if sym_st["losses"] >= BLACKLIST_LOSSES:
                    sym_st["paused_until"] = _t72.time() + 24 * 3600
                    sym_st["losses"] = 0  # reset para próxima semana
                    logger.warning(
                        f"#72 {symbol}: {BLACKLIST_LOSSES} pérdidas consecutivas → "
                        f"pausado 24h"
                    )
                    tg.info(f"🚫 {symbol} pausado 24h ({BLACKLIST_LOSSES} pérdidas consecutivas)")
            else:
                sym_st["losses"] = 0   # trade ganador resetea el contador

            # Registrar también en consecutive losses global
            self.record_trade_result(pnl_real)

            # Eliminar del rastreador de position management
            self._managed_positions.pop(ticket, None)

        # Actualizar el tracking para el próximo tick
        self._prev_tickets         = current_tickets
        self._prev_positions_map   = {p["ticket"]: p for p in current_positions}

    # ─── Estado y logs ────────────────────────────────────────────────────────

    def _update_equity(self) -> None:
        """Actualiza el equity del portfolio desde MT5 y detecta trades cerrados."""
        acc = self.connector.get_account_info()
        if acc:
            prev_equity = self.portfolio.equity
            self.portfolio.update_equity(acc["equity"])

            # #60 — Detectar posiciones cerradas (TP/SL/manual) y registrar P&L real
            positions = self.connector.get_open_positions()
            self._detect_closed_positions(positions)
            open_count = len(positions)

            # Fallback legacy: cambio de equity significativo → registrar para consecutive losses
            equity_delta = acc["equity"] - prev_equity
            if abs(equity_delta) > 0.50 and open_count < getattr(self, "_prev_open_count", open_count):
                self.record_trade_result(equity_delta)
            self._prev_open_count = open_count

            # #71 — Equity Curve Smoothing: registrar equity y detectar régimen
            self._equity_history.append(acc["equity"])
            if len(self._equity_history) > 50:
                self._equity_history.pop(0)
            if len(self._equity_history) >= 20:
                eq_ma20 = sum(self._equity_history[-20:]) / 20
                new_regime = "bearish" if acc["equity"] < eq_ma20 else "normal"
                if new_regime != self._equity_regime:
                    self._equity_regime = new_regime
                    if new_regime == "bearish":
                        logger.warning(
                            f"#71 Equity por debajo de MA20 (${eq_ma20:.2f}) → "
                            f"modo CONSERVADOR activo (confidence −20%)"
                        )
                        tg.info(f"📉 Equity bajo MA20 — modo conservador activado")
                    else:
                        logger.info(f"#71 Equity recuperó MA20 (${eq_ma20:.2f}) → modo NORMAL")

            daily_loss = (self._equity_at_day_open - acc["equity"]) / max(self._equity_at_day_open, 1)
            logger.info(
                f"Cuenta | Balance=${acc['balance']:.2f} | Equity=${acc['equity']:.2f} | "
                f"DD={self.portfolio.drawdown_pct:.2f}% | "
                f"PérdidaDía={daily_loss:.1%} | "
                f"Posiciones: {open_count} | "
                f"Losses consec: {self._consecutive_losses} | "
                f"Regime: {self._equity_regime}"
            )

    def _write_funnel_snapshot(self) -> None:
        """Persiste contadores del funnel de señales para la checklist del comité."""
        try:
            gen = self._signal_funnel.get("generated", 0) or 0
            exe = self._signal_funnel.get("executed", 0) or 0
            ratio = (exe / gen) if gen else 0.0
            payload = {
                **self._signal_funnel,
                "executed_ratio": round(ratio, 4),
                "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._FUNNEL_JSON.parent.mkdir(parents=True, exist_ok=True)
            self._FUNNEL_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as _fe:
            logger.debug(f"signal_funnel write: {_fe}")

    def _log_open_positions(self) -> None:
        """Loguea el estado de posiciones abiertas."""
        positions = self.connector.get_open_positions()
        if not positions:
            return
        logger.info(f"--- {len(positions)} posición(es) abierta(s) ---")
        for p in positions:
            pnl_sign = "+" if p["profit"] >= 0 else ""
            logger.info(
                f"  {p['direction']} {p['volume']} {p['symbol']} "
                f"@ {p['open_price']} | PnL: {pnl_sign}${p['profit']:.2f}"
            )

    def _print_session_summary(self) -> None:
        """Resumen de la sesión al cerrar."""
        summary = self.sizer.get_status_summary()
        logger.info("=" * 65)
        logger.info("  RESUMEN DE SESIÓN — MQ26 BOT v2 [S03 v3]")
        logger.info(f"  Equity final:    ${summary['equity']:.2f}")
        logger.info(f"  P&L del día:     ${summary['daily_pnl_usd']:.2f}")
        logger.info(f"  Trades hoy:      {summary['trades_today']}")
        logger.info(f"  DD máximo:       {summary['drawdown_pct']:.2f}%")
        logger.info("=" * 65)

        from datetime import datetime, timezone
        pnl_pct = summary["daily_pnl_usd"] / self.capital * 100
        wr = summary.get("win_rate_today", 0)
        tg.daily_report(
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            trades=summary["trades_today"],
            pnl_usd=summary["daily_pnl_usd"],
            pnl_pct=pnl_pct,
            win_rate=wr,
            equity=summary["equity"],
            dd_pct=summary["drawdown_pct"],
        )


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MQ26 BOT v2 — Demo Trading | S03 v3 Asian Range | Top 8 IC Markets"
    )
    parser.add_argument(
        "--symbol", "-s",
        nargs="+",
        default=DEFAULT_SYMBOLS,
        help="Símbolos a operar (default: Top 8). BTCUSD/ETHUSD=24/7, resto=Lun-Vie.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo loguea señales, no envía órdenes reales",
    )
    parser.add_argument(
        "--capital", "-c",
        type=float,
        default=2000.0,
        help="Capital inicial en USD (default: 2000)",
    )
    args = parser.parse_args()

    Path("data/logs").mkdir(parents=True, exist_ok=True)
    trader = DemoTrader(symbols=args.symbol, dry_run=args.dry_run, capital=args.capital)
    trader.start()


if __name__ == "__main__":
    main()
