"""
Position Sizer — Gestión de riesgo en 5 capas.

Capa 1: Riesgo por trade (% del capital)
Capa 2: Límites por sesión (pérdida diaria, trades máximos)
Capa 3: Riesgo de portafolio (correlación entre posiciones)
Capa 4: Circuit breaker por drawdown
Capa 5: Filtro de calendario (noticias alto impacto)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum, auto
from typing import Optional

from config.instruments import Instrument, price_to_pips
from config.settings import settings
from strategies.base import Signal, SignalDirection

logger = logging.getLogger(__name__)


class BotMode(Enum):
    NORMAL     = auto()   # Operación normal
    DEFENSIVE  = auto()   # DD >= 5%: size al 50%
    SCALP_ONLY = auto()   # DD >= 8%: solo scalping con size mínimo
    STOPPED    = auto()   # DD >= 12%: bot detenido


@dataclass
class SessionStats:
    """Estadísticas de la sesión actual (se reinicia cada día)."""
    date: date = field(default_factory=date.today)
    trades_count: int = 0
    daily_pnl_usd: float = 0.0
    consecutive_losses: int = 0
    paused_until: Optional[datetime] = None
    stopped: bool = False

    # #16 — Circuit breaker semanal
    week_number: int = field(default_factory=lambda: date.today().isocalendar()[1])
    weekly_pnl_usd: float = 0.0
    weekly_paused: bool = False   # True si esta semana superó el límite

    # #9 — Para Kelly: historial de resultados recientes
    recent_wins: int = 0
    recent_losses: int = 0
    recent_total_rr: float = 0.0   # suma de R:R de trades ganadores

    def reset_if_new_day(self) -> None:
        today = date.today()
        current_week = today.isocalendar()[1]

        # Reset diario
        if self.date != today:
            self.date = today
            self.trades_count = 0
            self.daily_pnl_usd = 0.0
            self.consecutive_losses = 0
            self.paused_until = None
            self.stopped = False

        # Reset semanal (lunes nuevo)
        if self.week_number != current_week:
            self.week_number = current_week
            self.weekly_pnl_usd = 0.0
            self.weekly_paused = False   # nueva semana, pausa levantada

    @property
    def kelly_risk_pct(self) -> Optional[float]:
        """#9 — Half-Kelly óptimo basado en trades recientes (mín 10 trades)."""
        total = self.recent_wins + self.recent_losses
        if total < 10:
            return None   # Insuficientes datos → usar risk_per_trade_pct fijo
        wr = self.recent_wins / total
        avg_rr = self.recent_total_rr / self.recent_wins if self.recent_wins > 0 else 1.0
        kelly = (wr * avg_rr - (1 - wr)) / avg_rr if avg_rr > 0 else 0
        kelly_half = kelly * 0.5   # Half-Kelly para seguridad
        return max(0.3, min(kelly_half * 100, 2.0))   # clamp 0.3% – 2.0%


@dataclass
class PortfolioState:
    """Estado actual del portafolio para cálculos de correlación y riesgo."""
    capital: float = 10_000.0
    equity: float = 10_000.0
    peak_equity: float = 10_000.0
    open_positions: list[Signal] = field(default_factory=list)
    total_risk_pct: float = 0.0    # Riesgo total de posiciones abiertas

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return (self.peak_equity - self.equity) / self.peak_equity * 100

    @property
    def ratchet_capital(self) -> float:
        """
        Capital ajustado con ratchet asimétrico:

        - Cuenta crece → sizing sube al 100% (compuesto completo)
        - Cuenta baja  → sizing baja al 50% de velocidad

        Ejemplo con $200 de pico:
          equity $200 (0% DD) → ratchet $200.00  (= equity)
          equity $190 (5% DD) → ratchet $195.00  (pierde 2.5%)
          equity $180 (10% DD)→ ratchet $190.00  (pierde 5%)
          equity $160 (20% DD)→ ratchet $180.00  (pierde 10%)

        Efecto: en drawdown se mantienen lotes más grandes
        para recuperar más rápido. El kill switch protege
        contra pérdidas extremas.
        """
        if self.equity >= self.peak_equity:
            return self.equity  # en máximo histórico: compuesto completo
        # En drawdown: reducción a mitad de velocidad
        dd_real = (self.peak_equity - self.equity) / self.peak_equity  # 0..1
        ratchet_factor = 1.0 - dd_real * 0.5
        return self.peak_equity * ratchet_factor

    def update_equity(self, equity: float) -> None:
        self.equity = equity
        if equity > self.peak_equity:
            self.peak_equity = equity

    def get_bot_mode(self) -> BotMode:
        dd = self.drawdown_pct
        risk_cfg = settings.risk
        if dd >= risk_cfg.dd_kill_switch_pct:
            return BotMode.STOPPED
        if dd >= risk_cfg.dd_scalping_only_pct:
            return BotMode.SCALP_ONLY
        if dd >= risk_cfg.dd_defensive_pct:
            return BotMode.DEFENSIVE
        return BotMode.NORMAL


@dataclass
class SizingResult:
    """Resultado del cálculo de tamaño de posición."""
    approved: bool
    lot_size: float = 0.0
    risk_usd: float = 0.0
    risk_pct: float = 0.0
    rejection_reason: str = ""


class PositionSizer:
    """
    Calcula el tamaño de posición óptimo respetando las 5 capas de riesgo.
    """

    def __init__(self, portfolio: PortfolioState):
        self.portfolio = portfolio
        self.session = SessionStats()
        self.risk_cfg = settings.risk

    def calculate_size(
        self,
        signal: Signal,
        instrument: Instrument,
        current_time: Optional[datetime] = None,
    ) -> SizingResult:
        """
        Punto de entrada principal. Verifica todas las capas y calcula el lot size.

        Args:
            signal:       Señal de la estrategia
            instrument:   Especificaciones del instrumento
            current_time: Momento actual (para filtros de sesión y calendario)

        Returns:
            SizingResult con lot_size=0 si la señal fue rechazada
        """
        self.session.reset_if_new_day()
        cfg = self.risk_cfg

        # ─── CAPA 4: Circuit breaker por drawdown ──────────────────────────
        mode = self.portfolio.get_bot_mode()
        if mode == BotMode.STOPPED:
            return SizingResult(
                approved=False,
                rejection_reason=f"KILL SWITCH: DD={self.portfolio.drawdown_pct:.1f}%"
            )

        # ─── CAPA 2b: Circuit breaker semanal (#16) ────────────────────────
        if self.session.weekly_paused:
            return SizingResult(
                approved=False,
                rejection_reason=f"CIRCUIT BREAKER SEMANAL: pérdida semana=${self.session.weekly_pnl_usd:.2f}"
            )

        # ─── CAPA 2: Límites de sesión ──────────────────────────────────────
        if self.session.stopped:
            return SizingResult(
                approved=False,
                rejection_reason=f"Sesión detenida: pérdida diaria={self.session.daily_pnl_usd:.2f} USD"
            )

        if self.session.paused_until and current_time:
            if datetime.now() < self.session.paused_until:
                return SizingResult(
                    approved=False,
                    rejection_reason=f"Pausa activa hasta {self.session.paused_until.strftime('%H:%M')}"
                )
            else:
                self.session.paused_until = None  # Pausa terminó

        if self.session.trades_count >= cfg.max_trades_per_session:
            return SizingResult(
                approved=False,
                rejection_reason=f"Máximo de trades por sesión alcanzado ({cfg.max_trades_per_session})"
            )

        # ─── CAPA 3: Límite de posiciones abiertas ─────────────────────────
        if len(self.portfolio.open_positions) >= cfg.max_open_positions:
            return SizingResult(
                approved=False,
                rejection_reason=f"Máximo de posiciones abiertas ({cfg.max_open_positions})"
            )

        # ─── CAPA 1: Riesgo por trade (con Kelly si hay datos suficientes) ──
        base_risk_pct = self._get_base_risk_pct(signal, mode)
        # #9 — Kelly Fraccionario: reemplaza base si hay ≥10 trades históricos
        kelly_pct = self.session.kelly_risk_pct
        if kelly_pct is not None:
            base_risk_pct = kelly_pct
            logger.debug(f"Kelly activo: {kelly_pct:.2f}% (WR={self.session.recent_wins}/{self.session.recent_wins+self.session.recent_losses})")
        adjusted_risk_pct = base_risk_pct * signal.confidence

        # #63 — Session-Based Risk Adjustment
        session_mult = self._get_session_multiplier(current_time)
        if session_mult != 1.0:
            logger.debug(f"#63 Session risk mult: ×{session_mult:.2f} → {adjusted_risk_pct * session_mult:.2f}%")
        adjusted_risk_pct *= session_mult

        # Ratchet asimétrico: sube al 100%, baja al 50% de velocidad
        risk_usd = self.portfolio.ratchet_capital * (adjusted_risk_pct / 100)
        lot_size = self._compute_lot_size(signal, instrument, risk_usd)

        if lot_size < instrument.min_lot:
            return SizingResult(
                approved=False,
                rejection_reason=f"Lot size calculado ({lot_size:.4f}) < mínimo ({instrument.min_lot})"
            )

        # Redondear al step de lote
        lot_size = self._normalize_lot(lot_size, instrument)

        return SizingResult(
            approved=True,
            lot_size=lot_size,
            risk_usd=risk_usd,
            risk_pct=adjusted_risk_pct,
        )

    def _get_base_risk_pct(self, signal: Signal, mode: BotMode) -> float:
        """Determina el % de riesgo base según el modo del bot y la estrategia."""
        cfg = self.risk_cfg

        if mode == BotMode.SCALP_ONLY:
            return 0.25  # Modo supervivencia

        # Scalping puro — solo M1 (muy corto plazo, SL pequeño)
        if signal.timeframe in ("M1",):
            base = cfg.scalping_risk_pct
        # S03 Asian Range en M5 — NO es scalping, es intraday con R:R 2-6x
        # Swing (FVG en H1/M15)
        elif signal.timeframe in ("M5", "H1", "H4", "D1", "M15"):
            base = cfg.risk_per_trade_pct  # 1% completo para S03
        else:
            base = cfg.risk_per_trade_pct

        # Modo defensivo: size al 50%
        if mode == BotMode.DEFENSIVE:
            base *= 0.5

        return base

    def _get_session_multiplier(self, current_time: Optional[datetime]) -> float:
        """
        #63 — Session-Based Risk Adjustment.

        Ajusta el tamaño de posición según la sesión de mercado activa (UTC):
          - Asiática  00:00–07:00 → ×0.80 (liquidez reducida, spreads más altos)
          - Londres   07:00–12:00 → ×1.10 (mayor liquidez, mejores fills)
          - NY overlap 12:00–15:00 → ×1.00 (neutral — ya tiene alta volatilidad)
          - NY tarde  15:00–21:00 → ×0.90 (caída de liquidez gradual)
          - Cierre     21:00–24:00 → ×0.70 (liquidez muy baja, avoid)

        Para crypto (24/7) aplica un factor fijo de 1.0 (no hay sesiones).
        """
        if current_time is None:
            return 1.0

        # Asegurarse de trabajar en UTC
        try:
            utc_time = current_time.astimezone(timezone.utc) if current_time.tzinfo else current_time
            hour = utc_time.hour
        except Exception:
            return 1.0

        # Mapeo hora UTC → multiplicador
        if   0  <= hour <  7:   return 0.80   # Sesión asiática
        elif 7  <= hour < 12:   return 1.10   # Sesión Londres (peak)
        elif 12 <= hour < 15:   return 1.00   # Overlap Londres/NY
        elif 15 <= hour < 21:   return 0.90   # NY tarde
        else:                   return 0.70   # Cierre mercados (21-24 UTC)

    def _compute_lot_size(
        self,
        signal: Signal,
        instrument: Instrument,
        risk_usd: float,
    ) -> float:
        """
        Calcula el lot size a partir del riesgo en USD y la distancia al SL.

        #62 — Commission-Aware Sizing:
          El riesgo neto descontado de comisión round-turn se itera una vez:
            lot_raw     = risk_usd / (sl_pips × pip_value)
            commission  = lot_raw × commission_rt
            net_risk    = risk_usd - commission
            lot_net     = net_risk / (sl_pips × pip_value)

        Para la mayoría de los pares el ajuste es ~1-2% del lote.
        Si commission_rt=0 (crypto/XAUUSD IC Markets) el resultado es idéntico.
        """
        sl_pips = price_to_pips(instrument, abs(signal.risk_pips))
        if sl_pips <= 0:
            return 0.0

        pip_value_per_lot = instrument.pip_value_usd
        denominator = sl_pips * pip_value_per_lot
        if denominator <= 0:
            return 0.0

        # Primera pasada (sin comisión)
        lot_raw = risk_usd / denominator

        # #62 — Descontar comisión round-turn si aplica
        commission_rt = getattr(instrument, "commission_rt", 3.50)
        if commission_rt > 0:
            commission_est = lot_raw * commission_rt
            net_risk = max(risk_usd - commission_est, risk_usd * 0.80)  # mín 80% del riesgo
            lot_size = net_risk / denominator
            if lot_size < lot_raw * 0.99:   # solo loguear si el ajuste es > 1%
                logger.debug(
                    f"#62 Commission-aware sizing | {instrument.symbol} | "
                    f"raw={lot_raw:.4f} → adj={lot_size:.4f} | "
                    f"commission=${commission_est:.2f}"
                )
        else:
            lot_size = lot_raw

        return lot_size

    def _normalize_lot(self, lot: float, instrument: Instrument) -> float:
        """Normaliza el lot al step permitido por el broker."""
        step = instrument.lot_step
        normalized = round(lot / step) * step
        return max(instrument.min_lot, normalized)

    def record_trade_open(self, signal: Signal) -> None:
        """Registra apertura de trade en las estadísticas de sesión."""
        self.session.trades_count += 1
        self.portfolio.open_positions.append(signal)

    def record_trade_close(self, pnl_usd: float, rr_achieved: float = 0.0) -> None:
        """Registra cierre de trade y actualiza estadísticas."""
        cfg = self.risk_cfg

        self.session.daily_pnl_usd += pnl_usd
        self.session.weekly_pnl_usd += pnl_usd
        self.portfolio.update_equity(self.portfolio.equity + pnl_usd)

        if pnl_usd < 0:
            self.session.consecutive_losses += 1
            self.session.recent_losses += 1
        else:
            self.session.consecutive_losses = 0
            self.session.recent_wins += 1
            self.session.recent_total_rr += max(rr_achieved, 1.0)

        # Mantener ventana reciente de 30 trades máximo (sliding window)
        total_recent = self.session.recent_wins + self.session.recent_losses
        if total_recent > 30:
            # Reducir proporcionalmente para no crecer indefinidamente
            factor = 29 / 30
            self.session.recent_wins   = round(self.session.recent_wins * factor)
            self.session.recent_losses = round(self.session.recent_losses * factor)
            self.session.recent_total_rr *= factor

        # Verificar pérdida máxima diaria
        daily_loss_limit = self.portfolio.capital * (cfg.max_daily_loss_pct / 100)
        if self.session.daily_pnl_usd < -daily_loss_limit:
            logger.warning(
                f"STOP DIARIO alcanzado: PnL={self.session.daily_pnl_usd:.2f} USD "
                f"(límite={-daily_loss_limit:.2f})"
            )
            self.session.stopped = True

        # #16 — Circuit breaker semanal: -5% de peak en la semana → pausa hasta lunes
        weekly_loss_limit = self.portfolio.peak_equity * 0.05
        if self.session.weekly_pnl_usd < -weekly_loss_limit and not self.session.weekly_paused:
            self.session.weekly_paused = True
            logger.warning(
                f"#16 CIRCUIT BREAKER SEMANAL: pérdida semana=${self.session.weekly_pnl_usd:.2f} "
                f"(límite=-${weekly_loss_limit:.2f}) — pausado hasta el lunes"
            )

        # Verificar pérdidas consecutivas → pausa
        if self.session.consecutive_losses >= cfg.consecutive_losses_pause:
            from datetime import timedelta
            pause_until = datetime.now() + timedelta(hours=2)
            self.session.paused_until = pause_until
            self.session.consecutive_losses = 0
            logger.warning(
                f"Pausa activada por {cfg.consecutive_losses_pause} pérdidas consecutivas. "
                f"Reanuda: {pause_until.strftime('%H:%M')}"
            )

    def get_status_summary(self) -> dict:
        """Resumen del estado del bot para el dashboard."""
        mode = self.portfolio.get_bot_mode()
        return {
            "mode": mode.name,
            "equity": self.portfolio.equity,
            "drawdown_pct": self.portfolio.drawdown_pct,
            "daily_pnl_usd": self.session.daily_pnl_usd,
            "trades_today": self.session.trades_count,
            "open_positions": len(self.portfolio.open_positions),
            "consecutive_losses": self.session.consecutive_losses,
            "session_stopped": self.session.stopped,
            "paused_until": str(self.session.paused_until) if self.session.paused_until else None,
        }
