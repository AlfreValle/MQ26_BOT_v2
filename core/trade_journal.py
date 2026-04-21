"""
#38 — Trade Journal SQLite

Registra todos los trades del bot en una base de datos SQLite local.
Permite análisis histórico, detección de patrones, y base para ML futuro.

Uso:
    from core.trade_journal import journal
    journal.record_open(ticket=123, symbol="AUDUSD", ...)
    journal.record_close(ticket=123, close_price=0.6550, pnl_usd=21.5)
    stats = journal.get_today_stats()
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("data/trade_journal.db")


class TradeJournal:
    """SQLite trade journal. Thread-safe con WAL mode."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Crea las tablas si no existen."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket      INTEGER UNIQUE,
                    symbol      TEXT NOT NULL,
                    direction   TEXT NOT NULL,         -- BUY | SELL
                    lot         REAL,
                    entry_price REAL,
                    sl_price    REAL,
                    tp1_price   REAL,
                    open_time   TEXT,
                    close_time  TEXT,
                    close_price REAL,
                    pnl_usd     REAL,
                    pnl_pips    REAL,
                    outcome     TEXT,                  -- tp1|tp2|sl|time_exit|manual
                    duration_h  REAL,
                    rr_achieved REAL,
                    equity_after REAL,
                    notes       TEXT,
                    created_at  TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS daily_summary (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    date        TEXT UNIQUE,
                    trades      INTEGER DEFAULT 0,
                    wins        INTEGER DEFAULT 0,
                    losses      INTEGER DEFAULT 0,
                    pnl_usd     REAL DEFAULT 0,
                    win_rate    REAL DEFAULT 0,
                    max_dd_pct  REAL DEFAULT 0,
                    equity_close REAL DEFAULT 0,
                    created_at  TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
                CREATE INDEX IF NOT EXISTS idx_trades_date   ON trades(open_time);
            """)
        logger.debug(f"Trade journal inicializado: {self.db_path}")

    # ─── Registro de trades ───────────────────────────────────────────────────

    def record_open(
        self,
        ticket: int,
        symbol: str,
        direction: str,
        lot: float,
        entry_price: float,
        sl_price: float,
        tp1_price: float,
        notes: str = "",
    ) -> None:
        """Registra apertura de trade."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO trades
                    (ticket, symbol, direction, lot, entry_price, sl_price, tp1_price, open_time, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ticket, symbol, direction, lot, entry_price, sl_price, tp1_price, now, notes))
            logger.debug(f"Journal: trade abierto #{ticket} {direction} {symbol}")
        except Exception as e:
            logger.warning(f"Journal: error registrando apertura {ticket}: {e}")

    def record_close(
        self,
        ticket: int,
        close_price: float,
        pnl_usd: float,
        outcome: str = "unknown",
        equity_after: float = 0.0,
    ) -> None:
        """Registra cierre de trade."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._conn() as conn:
                # Obtener datos de apertura para calcular métricas
                row = conn.execute(
                    "SELECT * FROM trades WHERE ticket=?", (ticket,)
                ).fetchone()

                if row is None:
                    logger.warning(f"Journal: ticket {ticket} no encontrado para cierre")
                    return

                open_dt  = datetime.fromisoformat(row["open_time"])
                close_dt = datetime.now(timezone.utc)
                duration_h = (close_dt - open_dt).total_seconds() / 3600

                # R:R real conseguido
                entry  = row["entry_price"] or 0
                sl     = row["sl_price"] or 0
                risk   = abs(entry - sl)
                gain   = abs(close_price - entry) if entry else 0
                rr_achieved = gain / risk if risk > 0 else 0

                # Pips
                if row["symbol"] in ("BTCUSD", "ETHUSD", "XAUUSD"):
                    pip_size = 1.0
                elif "JPY" in row["symbol"]:
                    pip_size = 0.01
                else:
                    pip_size = 0.0001
                pnl_pips = pnl_usd / (row["lot"] * 10) if row["lot"] else 0

                conn.execute("""
                    UPDATE trades SET
                        close_time=?, close_price=?, pnl_usd=?, pnl_pips=?,
                        outcome=?, duration_h=?, rr_achieved=?, equity_after=?
                    WHERE ticket=?
                """, (now, close_price, pnl_usd, pnl_pips,
                      outcome, duration_h, rr_achieved, equity_after, ticket))

            logger.debug(f"Journal: trade cerrado #{ticket} PnL=${pnl_usd:+.2f} ({outcome})")
        except Exception as e:
            logger.warning(f"Journal: error registrando cierre {ticket}: {e}")

    # ─── Estadísticas ─────────────────────────────────────────────────────────

    def get_today_stats(self) -> dict:
        """Estadísticas del día actual."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            with self._conn() as conn:
                rows = conn.execute("""
                    SELECT pnl_usd, outcome FROM trades
                    WHERE open_time LIKE ? AND close_time IS NOT NULL
                """, (f"{today}%",)).fetchall()

                total  = len(rows)
                wins   = sum(1 for r in rows if (r["pnl_usd"] or 0) > 0)
                pnl    = sum(r["pnl_usd"] or 0 for r in rows)
                wr     = wins / total if total > 0 else 0

                return {"date": today, "trades": total, "wins": wins,
                        "pnl_usd": pnl, "win_rate": wr}
        except Exception as e:
            logger.warning(f"Journal: error stats: {e}")
            return {"date": today, "trades": 0, "wins": 0, "pnl_usd": 0.0, "win_rate": 0.0}

    def get_all_stats(self) -> dict:
        """Estadísticas globales de todos los trades cerrados."""
        try:
            with self._conn() as conn:
                rows = conn.execute("""
                    SELECT pnl_usd, rr_achieved, duration_h, symbol
                    FROM trades WHERE close_time IS NOT NULL
                """).fetchall()

                total  = len(rows)
                if total == 0:
                    return {"total_trades": 0}
                wins   = sum(1 for r in rows if (r["pnl_usd"] or 0) > 0)
                pnl    = sum(r["pnl_usd"] or 0 for r in rows)
                avg_rr = sum(r["rr_achieved"] or 0 for r in rows) / total

                return {
                    "total_trades": total,
                    "wins": wins,
                    "losses": total - wins,
                    "win_rate": wins / total,
                    "total_pnl_usd": pnl,
                    "avg_rr": avg_rr,
                }
        except Exception as e:
            logger.warning(f"Journal: error all stats: {e}")
            return {}

    # ─── #61 Trade Analytics ──────────────────────────────────────────────────

    def get_weekly_stats(self) -> dict:
        """#61 — Estadísticas de los últimos 7 días calendario."""
        from datetime import timedelta
        today = datetime.now(timezone.utc).date()
        week_start = (today - timedelta(days=6)).isoformat()
        try:
            with self._conn() as conn:
                rows = conn.execute("""
                    SELECT symbol, direction, pnl_usd, rr_achieved, duration_h, outcome
                    FROM trades
                    WHERE close_time IS NOT NULL
                      AND date(open_time) >= ?
                """, (week_start,)).fetchall()

                total = len(rows)
                if total == 0:
                    return {"period": f"{week_start} → {today}", "total_trades": 0}

                wins    = sum(1 for r in rows if (r["pnl_usd"] or 0) > 0)
                losses  = total - wins
                pnl     = sum(r["pnl_usd"] or 0 for r in rows)
                avg_rr  = sum(r["rr_achieved"] or 0 for r in rows) / total
                avg_dur = sum(r["duration_h"]  or 0 for r in rows) / total

                # Desglose por símbolo
                by_symbol: dict[str, dict] = {}
                for r in rows:
                    sym = r["symbol"]
                    if sym not in by_symbol:
                        by_symbol[sym] = {"trades": 0, "wins": 0, "pnl": 0.0}
                    by_symbol[sym]["trades"] += 1
                    by_symbol[sym]["pnl"]    += r["pnl_usd"] or 0
                    if (r["pnl_usd"] or 0) > 0:
                        by_symbol[sym]["wins"] += 1

                # Outcome breakdown
                outcomes = {}
                for r in rows:
                    oc = r["outcome"] or "unknown"
                    outcomes[oc] = outcomes.get(oc, 0) + 1

                return {
                    "period":        f"{week_start} → {today}",
                    "total_trades":  total,
                    "wins":          wins,
                    "losses":        losses,
                    "win_rate":      round(wins / total, 3),
                    "total_pnl_usd": round(pnl, 2),
                    "avg_rr":        round(avg_rr, 2),
                    "avg_duration_h": round(avg_dur, 2),
                    "by_symbol":     by_symbol,
                    "outcomes":      outcomes,
                }
        except Exception as e:
            logger.warning(f"Journal: error weekly stats: {e}")
            return {}

    def update_daily_summary(self, equity_close: float, max_dd_pct: float = 0.0) -> None:
        """#61 — Actualiza (o crea) el resumen del día en daily_summary table."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            stats = self.get_today_stats()
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO daily_summary (date, trades, wins, losses, pnl_usd, win_rate, max_dd_pct, equity_close)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                        trades      = excluded.trades,
                        wins        = excluded.wins,
                        losses      = excluded.losses,
                        pnl_usd     = excluded.pnl_usd,
                        win_rate    = excluded.win_rate,
                        max_dd_pct  = excluded.max_dd_pct,
                        equity_close = excluded.equity_close
                """, (
                    today,
                    stats["trades"],
                    stats["wins"],
                    stats["trades"] - stats["wins"],
                    round(stats["pnl_usd"], 2),
                    round(stats["win_rate"], 4),
                    round(max_dd_pct, 4),
                    round(equity_close, 2),
                ))
            logger.debug(f"Journal: daily_summary actualizado para {today}")
        except Exception as e:
            logger.warning(f"Journal: error update_daily_summary: {e}")

    def get_symbol_stats(self, symbol: str, days: int = 30) -> dict:
        """#61 — Estadísticas por símbolo en los últimos N días."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
        try:
            with self._conn() as conn:
                rows = conn.execute("""
                    SELECT pnl_usd, rr_achieved, duration_h, outcome
                    FROM trades
                    WHERE symbol=? AND close_time IS NOT NULL AND date(open_time) >= ?
                """, (symbol, cutoff)).fetchall()

                total = len(rows)
                if total == 0:
                    return {"symbol": symbol, "trades": 0}

                wins  = sum(1 for r in rows if (r["pnl_usd"] or 0) > 0)
                pnl   = sum(r["pnl_usd"] or 0 for r in rows)
                avg_rr = sum(r["rr_achieved"] or 0 for r in rows) / total

                return {
                    "symbol":        symbol,
                    "days":          days,
                    "trades":        total,
                    "wins":          wins,
                    "losses":        total - wins,
                    "win_rate":      round(wins / total, 3),
                    "total_pnl_usd": round(pnl, 2),
                    "avg_rr":        round(avg_rr, 2),
                    "expectancy":    round(pnl / total, 2),
                }
        except Exception as e:
            logger.warning(f"Journal: error symbol stats {symbol}: {e}")
            return {"symbol": symbol, "trades": 0}


# Singleton global
journal = TradeJournal()
