"""
Alertas por Telegram — MQ26 BOT v2

Envía notificaciones en tiempo real sobre:
  - Señal detectada (LONG/SHORT)
  - Orden ejecutada
  - Take Profit alcanzado (TP1 / TP2)
  - Stop Loss tocado
  - Kill switch activado
  - Reporte diario de P&L

Setup:
  1. Hablar con @BotFather en Telegram → /newbot → copiar token
  2. Iniciar chat con tu bot → obtener chat_id:
     https://api.telegram.org/bot<TOKEN>/getUpdates
  3. Agregar al .env:
       TG_TOKEN=123456789:AAF...
       TG_CHAT_ID=-100123456789
       TG_ENABLED=true
"""
from __future__ import annotations

import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ─── Emojis por tipo de evento ────────────────────────────────────────────────
EMOJI = {
    "signal_long":  "🟢",
    "signal_short": "🔴",
    "order_ok":     "✅",
    "tp1":          "🎯",
    "tp2":          "🏆",
    "sl":           "❌",
    "trail":        "📈",
    "kill":         "🚨",
    "daily":        "📊",
    "blackout":     "⏸️",
    "info":         "ℹ️",
    "warning":      "⚠️",
}


class TelegramAlerter:
    """Envia mensajes al bot de Telegram. Thread-safe (solo HTTP)."""

    def __init__(self, token: str = "", chat_id: str = "", enabled: bool = False):
        self.token   = token
        self.chat_id = chat_id
        self.enabled = enabled and bool(token) and bool(chat_id)

        if enabled and not self.enabled:
            logger.warning("Telegram habilitado pero faltan token/chat_id — desactivado")

    def send(self, text: str, silent: bool = False) -> bool:
        """Envía un mensaje. Retorna True si tuvo éxito."""
        if not self.enabled:
            return False
        try:
            url     = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = urllib.parse.urlencode({
                "chat_id":              self.chat_id,
                "text":                 text,
                "parse_mode":           "HTML",
                "disable_notification": silent,
            }).encode()
            req = urllib.request.Request(url, data=payload, method="POST")
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception as e:
            logger.debug(f"Telegram send error: {e}")
            return False

    # ─── Mensajes específicos ─────────────────────────────────────────────────

    def signal_detected(
        self,
        symbol: str,
        direction: str,
        entry: float,
        sl: float,
        tp1: float,
        tp2: float,
        rr: float,
        notes: str = "",
    ) -> None:
        emoji = EMOJI["signal_long"] if direction == "LONG" else EMOJI["signal_short"]
        risk  = abs(entry - sl)
        msg   = (
            f"{emoji} <b>SEÑAL {direction}</b> — <code>{symbol}</code>\n"
            f"┌ Entry:  <code>{entry:.5f}</code>\n"
            f"├ SL:     <code>{sl:.5f}</code>  (-{risk:.5f})\n"
            f"├ TP1:    <code>{tp1:.5f}</code>\n"
            f"└ TP2:    <code>{tp2:.5f}</code>  R:R {rr:.1f}x\n"
            f"<i>{notes}</i>"
        )
        self.send(msg)

    def order_executed(
        self,
        symbol: str,
        direction: str,
        lot: float,
        price: float,
        ticket: int,
        risk_usd: float,
    ) -> None:
        msg = (
            f"{EMOJI['order_ok']} <b>ORDEN EJECUTADA</b>\n"
            f"<code>{direction} {lot:.2f} {symbol} @ {price:.5f}</code>\n"
            f"Ticket: <code>{ticket}</code>  |  Riesgo: <b>${risk_usd:.2f}</b>"
        )
        self.send(msg)

    def trade_closed(
        self,
        symbol: str,
        direction: str,
        outcome: str,
        pnl_usd: float,
        pnl_pips: float,
        duration_h: float,
    ) -> None:
        if outcome in ("tp2", "tp1"):
            emoji = EMOJI["tp2"]
            label = "TAKE PROFIT ✓"
        elif outcome == "trail":
            emoji = EMOJI["trail"]
            label = "TRAILING STOP"
        elif outcome == "be":
            emoji = EMOJI["tp1"]
            label = "BREAKEVEN"
        else:
            emoji = EMOJI["sl"]
            label = "STOP LOSS"

        sign  = "+" if pnl_usd >= 0 else ""
        color = "🟩" if pnl_usd >= 0 else "🟥"
        msg   = (
            f"{emoji} <b>{label}</b> — <code>{symbol}</code>\n"
            f"{color} P&amp;L: <b>{sign}${pnl_usd:.2f}</b>  ({sign}{pnl_pips:.1f} pips)\n"
            f"Duración: {duration_h:.1f}h"
        )
        self.send(msg)

    def kill_switch(self, dd_pct: float, equity: float) -> None:
        msg = (
            f"{EMOJI['kill']} <b>KILL SWITCH ACTIVADO</b>\n"
            f"DD: <b>{dd_pct:.1f}%</b>  |  Equity: ${equity:.2f}\n"
            f"Todas las posiciones cerradas. Bot detenido."
        )
        self.send(msg, silent=False)

    def daily_report(
        self,
        date: str,
        trades: int,
        pnl_usd: float,
        pnl_pct: float,
        win_rate: float,
        equity: float,
        dd_pct: float,
        weekly_stats: dict | None = None,
        by_symbol: dict | None = None,
    ) -> None:
        """#67 — Reporte diario mejorado con estadísticas semanales y desglose por símbolo."""
        sign  = "+" if pnl_usd >= 0 else ""
        color = "🟢" if pnl_usd >= 0 else "🔴"
        losses = max(0, trades - round(trades * win_rate))

        msg_lines = [
            f"{EMOJI['daily']} <b>REPORTE DIARIO</b> — {date}",
            "─" * 28,
            f"{color} P&amp;L: <b>{sign}${pnl_usd:.2f}</b> ({sign}{pnl_pct:.1f}%)",
            f"📊 Trades: {trades}  |  WR: {win_rate:.0%}  (✅{trades - losses} / ❌{losses})",
            f"💼 Equity: ${equity:.2f}  |  📉 DD: {dd_pct:.1f}%",
        ]

        # Desglose por símbolo (#67)
        if by_symbol:
            sym_lines = []
            for sym, st in sorted(by_symbol.items(), key=lambda x: -abs(x[1].get("pnl", 0))):
                sym_pnl  = st.get("pnl", 0)
                sym_tr   = st.get("trades", 0)
                sym_wr   = st.get("wins", 0) / sym_tr if sym_tr > 0 else 0
                sym_sign = "+" if sym_pnl >= 0 else ""
                emoji    = "🟢" if sym_pnl >= 0 else "🔴"
                sym_lines.append(f"  {emoji} {sym}: {sym_sign}${sym_pnl:.2f} ({sym_wr:.0%} WR, {sym_tr}t)")
            if sym_lines:
                msg_lines += ["", "📌 <b>Por símbolo:</b>"] + sym_lines

        # Resumen semanal (#67)
        if weekly_stats and weekly_stats.get("total_trades", 0) > 0:
            w = weekly_stats
            w_sign  = "+" if w.get("total_pnl_usd", 0) >= 0 else ""
            w_color = "🟢" if w.get("total_pnl_usd", 0) >= 0 else "🔴"
            msg_lines += [
                "",
                "📅 <b>Semana:</b>",
                f"  {w_color} P&amp;L: {w_sign}${w.get('total_pnl_usd', 0):.2f}  |  "
                f"WR: {w.get('win_rate', 0):.0%}  |  "
                f"AvgRR: {w.get('avg_rr', 0):.2f}",
                f"  📊 {w.get('total_trades', 0)} trades ({w.get('wins', 0)}✅ / {w.get('losses', 0)}❌)",
            ]

        self.send("\n".join(msg_lines), silent=True)

    def blackout_notice(self, reason: str) -> None:
        msg = f"{EMOJI['blackout']} <b>BLACKOUT NOTICIAS</b>\n<i>{reason}</i>"
        self.send(msg, silent=True)

    def heartbeat(self, equity: float, positions: int, dd_pct: float) -> None:
        """#47 — Mensaje automático cada 6 horas para confirmar que el bot sigue activo."""
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
        dd_icon = "🟢" if dd_pct < 5 else ("🟡" if dd_pct < 10 else "🔴")
        msg = (
            f"💓 <b>BOT ACTIVO</b> — {now_str}\n"
            f"💼 Equity: <b>${equity:,.2f}</b>\n"
            f"📂 Posiciones abiertas: {positions}\n"
            f"{dd_icon} DD actual: {dd_pct:.1f}%"
        )
        self.send(msg, silent=True)

    def info(self, text: str) -> None:
        self.send(f"{EMOJI['info']} {text}", silent=True)


# ─── Singleton global ─────────────────────────────────────────────────────────
def build_alerter_from_settings() -> TelegramAlerter:
    """Construye el alerter desde config/settings.py."""
    try:
        from config.settings import settings
        return TelegramAlerter(
            token   = settings.telegram.token,
            chat_id = settings.telegram.chat_id,
            enabled = settings.telegram.enabled,
        )
    except Exception:
        return TelegramAlerter()  # deshabilitado


# Instancia global lista para importar
alerter = build_alerter_from_settings()
