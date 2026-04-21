"""
MT5 Connector — Conexión con MetaTrader 5 (IC Markets Demo)

Responsabilidades:
  - Conectar / desconectar de MT5
  - Obtener precios en tiempo real (bid/ask)
  - Descargar OHLCV histórico y en curso
  - Enviar órdenes de mercado con SL/TP
  - Monitorear posiciones abiertas
  - Kill switch de emergencia
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Import MT5 — puede no estar instalado en macOS/Linux
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 no instalado — modo simulado activo")

# Mapeo de timeframes MQ26 → constantes MT5
TF_MAP = {
    "M1":  1,    # mt5.TIMEFRAME_M1
    "M5":  5,    # mt5.TIMEFRAME_M5
    "M15": 15,
    "M30": 30,
    "H1":  16385,  # mt5.TIMEFRAME_H1
    "H4":  16388,
    "D1":  16408,
}


class MT5Connector:
    """
    Wrapper sobre la API de MetaTrader5 con manejo de errores,
    reconexión automática y kill switch.
    """

    # Rutas conocidas del terminal MT5 en Windows
    _TERMINAL_PATHS = [
        r"C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe",
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    ]

    def __init__(self):
        self._connected = False
        self._login  = int(os.getenv("MT5_LOGIN", "0"))
        self._passwd = os.getenv("MT5_PASSWORD", "")
        self._server = os.getenv("MT5_SERVER", "ICMarketsSC-Demo")
        self._timeout = int(os.getenv("MT5_TIMEOUT", "60000"))
        self._path   = os.getenv("MT5_PATH", "")  # opcional — ruta explícita al terminal

    # ─── Conexión ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Conecta a MT5 probando 3 estrategias en orden:
          1. Sin credenciales — usa la sesión ya activa en el terminal
          2. Con credenciales + path explícito al terminal64.exe
          3. Con credenciales sin path (deja que MT5 lo detecte)
        """
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 no esta instalado.")
            return False

        # Asegurar estado limpio
        try:
            mt5.shutdown()
        except Exception:
            pass

        # ── Estrategia 1: sesión ya activa (sin pasar credenciales) ──────────
        logger.info("MT5 connect: intentando con sesion activa del terminal...")
        if mt5.initialize(timeout=self._timeout):
            info = mt5.account_info()
            if info is not None:
                self._connected = True
                logger.info(
                    f"MT5 conectado (sesion activa) | Cuenta: {info.login} | "
                    f"Broker: {info.company} | Balance: ${info.balance:,.2f}"
                )
                return True
            mt5.shutdown()
            logger.warning(f"Estrategia 1 fallo: {mt5.last_error()}")

        # ── Estrategia 2: con credenciales + path explícito ──────────────────
        terminal_path = self._path or self._detect_terminal_path()
        if terminal_path:
            logger.info(f"MT5 connect: intentando con path={terminal_path}...")
            if mt5.initialize(
                path=terminal_path,
                login=self._login,
                password=self._passwd,
                server=self._server,
                timeout=self._timeout,
            ):
                info = mt5.account_info()
                if info is not None:
                    self._connected = True
                    logger.info(
                        f"MT5 conectado (path+credenciales) | Cuenta: {info.login} | "
                        f"Broker: {info.company} | Balance: ${info.balance:,.2f}"
                    )
                    return True
                mt5.shutdown()
            logger.warning(f"Estrategia 2 fallo: {mt5.last_error()}")

        # ── Estrategia 3: credenciales sin path ──────────────────────────────
        logger.info("MT5 connect: intentando con credenciales sin path...")
        if mt5.initialize(
            login=self._login,
            password=self._passwd,
            server=self._server,
            timeout=self._timeout,
        ):
            info = mt5.account_info()
            if info is not None:
                self._connected = True
                logger.info(
                    f"MT5 conectado (credenciales) | Cuenta: {info.login} | "
                    f"Broker: {info.company} | Balance: ${info.balance:,.2f}"
                )
                return True
            mt5.shutdown()

        err = mt5.last_error()
        logger.error(
            f"MT5: todas las estrategias fallaron. Ultimo error: {err}\n"
            f"  Verificar:\n"
            f"  1. MT5 abierto y logueado a cuenta {self._login}\n"
            f"  2. Tools > Options > Expert Advisors > 'Allow automated trading' habilitado\n"
            f"  3. El servidor '{self._server}' es el correcto (ver esquina inferior derecha del terminal)"
        )
        return False

    def _detect_terminal_path(self) -> str:
        """Detecta la ruta del terminal MT5 entre las ubicaciones conocidas."""
        from pathlib import Path
        for p in self._TERMINAL_PATHS:
            if Path(p).exists():
                logger.info(f"Terminal MT5 detectado en: {p}")
                return p
        logger.warning("No se detecto terminal MT5 en rutas conocidas")
        return ""

    def disconnect(self) -> None:
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("MT5 desconectado.")

    def is_connected(self) -> bool:
        if not MT5_AVAILABLE or not self._connected:
            return False
        return mt5.terminal_info() is not None

    def reconnect(self) -> bool:
        logger.warning("Intentando reconexión MT5...")
        self.disconnect()
        return self.connect()

    def check_autotrading(self) -> bool:
        """Verifica si AutoTrading está habilitado en el terminal MT5."""
        if not MT5_AVAILABLE or not self._connected:
            return False
        terminal = mt5.terminal_info()
        if terminal is None:
            return False
        return bool(terminal.trade_allowed)

    # ─── Info de cuenta ──────────────────────────────────────────────────────

    def get_account_info(self) -> Optional[dict]:
        if not self._check(): return None
        info = mt5.account_info()
        if info is None: return None
        return {
            "login":        info.login,
            "balance":      info.balance,
            "equity":       info.equity,
            "margin":       info.margin,
            "free_margin":  info.margin_free,
            "margin_level": info.margin_level,
            "profit":       info.profit,
            "leverage":     info.leverage,
            "currency":     info.currency,
            "server":       info.server,
            "company":      info.company,
        }

    # ─── Precios en tiempo real ───────────────────────────────────────────────

    def get_tick(self, symbol: str) -> Optional[dict]:
        """Retorna el último tick (bid/ask/time) de un símbolo."""
        if not self._check(): return None
        # Asegurar que el símbolo esté visible en Market Watch
        info = mt5.symbol_info(symbol)
        if info is not None and not info.visible:
            mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.warning(f"Sin tick para {symbol}")
            return None
        return {
            "symbol": symbol,
            "bid":    tick.bid,
            "ask":    tick.ask,
            "spread": round((tick.ask - tick.bid) / self._get_pip_size(symbol), 1),
            "time":   datetime.fromtimestamp(tick.time, tz=timezone.utc),
        }

    def get_ticks_multi(self, symbols: list[str]) -> dict[str, dict]:
        """Retorna ticks para múltiples símbolos en una sola llamada."""
        return {s: self.get_tick(s) for s in symbols if self.get_tick(s) is not None}

    # ─── OHLCV histórico ─────────────────────────────────────────────────────

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "M5",
        n_bars: int = 500,
    ) -> pd.DataFrame:
        """
        Descarga las últimas n_bars velas de MT5.

        Returns:
            DataFrame con columnas: open, high, low, close, volume
            Index: DatetimeTZ en UTC
        """
        if not self._check():
            return pd.DataFrame()

        tf_const = self._resolve_timeframe(timeframe)
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, n_bars)

        if rates is None or len(rates) == 0:
            logger.warning(f"Sin datos OHLCV para {symbol} {timeframe}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("time").rename(columns={
            "open": "open", "high": "high", "low": "low",
            "close": "close", "tick_volume": "volume",
        })
        df = df[["open", "high", "low", "close", "volume"]].sort_index()
        return df

    # ─── Órdenes ─────────────────────────────────────────────────────────────

    # #7/#64 — Spread máximo estático por símbolo (pips en la fórmula (ask-bid)/point/10)
    # Valores calibrados para IC Markets Raw Spread:
    #   Forex majors: ~1-3 pips normales, max 3-5× ese valor
    #   XAUUSD: (ask-bid=0.5)/0.01/10 = 5 pips normales → max 50
    #   BTCUSD: (ask-bid=80)/1/10 = 8 pips normales → max 80
    #   ETHUSD: (ask-bid=0.5)/0.01/10 = 5 pips normales → max 50
    # Umbral máximo de spread por símbolo (en pips: (ask-bid)/point/10)
    # BTCUSD: sesión NY cierre (22–23 UTC) → spread típico $120 = 120 "pips" con point=0.1
    #         Londres peak → spread $30–60 = 30–60 pips. Máximo 200 cubre holgadamente.
    _MAX_SPREAD: dict[str, float] = {
        "AUDUSD": 3.0,  "NZDUSD": 4.0,  "GBPUSD": 4.0,  "EURUSD": 3.0,
        "AUDJPY": 5.0,  "USDJPY": 4.0,  "GBPJPY": 8.0,
        "XAUUSD": 50.0, "BTCUSD": 200.0, "ETHUSD": 100.0,
    }

    def check_spread(self, symbol: str, atr_pips: float = 0.0) -> tuple[bool, float]:
        """
        #7/#64 — Verifica que el spread actual no sea excesivo.

        Spread se calcula como: (ask - bid) / point / 10  [en "pips" de 5 decimales]
        Para XAUUSD: point=0.01 → (ask-bid=0.50) / 0.01 / 10 = 5 "pips"

        #64 — Dynamic Spread Threshold:
          Si se provee atr_pips, max_spread = max(static_max, atr_pips × 0.15)
          Esto permite spreads más amplios durante alta volatilidad.

        Retorna (ok, spread_actual).
        """
        if not self._check():
            return True, 0.0  # no bloquear si no hay datos
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            return True, 0.0
        spread = (tick.ask - tick.bid) / info.point / 10  # en pips

        # Umbral estático desde _MAX_SPREAD (valores calibrados, sin dependencia externa)
        static_max = self._MAX_SPREAD.get(symbol, 10.0)

        # #64 — Dynamic threshold basado en ATR
        ATR_SPREAD_RATIO = 0.15
        dynamic_max = max(static_max, atr_pips * ATR_SPREAD_RATIO) if atr_pips > 0 else static_max

        ok = spread <= dynamic_max
        if not ok and atr_pips > 0:
            logger.debug(
                f"#64 {symbol}: spread={spread:.1f} | static={static_max:.1f} | "
                f"dynamic={dynamic_max:.1f} | atr={atr_pips:.1f}"
            )
        return ok, spread

    def send_market_order(
        self,
        symbol: str,
        direction: str,     # "BUY" | "SELL"
        lot_size: float,
        sl_price: float,
        tp1_price: float,
        tp2_price: Optional[float] = None,
        comment: str = "MQ26v2",
        magic: int = 26042026,
    ) -> Optional[dict]:
        """
        Envía una orden de mercado con SL y TP.
        En modo demo, ejecuta igual pero sin dinero real.

        Returns:
            dict con resultado de la orden, o None si falló
        """
        if not self._check(): return None

        sym_info = mt5.symbol_info(symbol)
        if sym_info is None:
            logger.error(f"Símbolo no encontrado: {symbol}")
            return None

        if not sym_info.visible:
            mt5.symbol_select(symbol, True)

        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        tick       = mt5.symbol_info_tick(symbol)
        price      = tick.ask if direction == "BUY" else tick.bid
        deviation  = 30  # slippage en puntos

        # ── Validar que SL/TP estén del lado correcto del precio actual ─────
        # Evita retcode=10016 cuando el mercado se movió desde que se generó la señal
        if direction == "BUY":
            sl_valid = sl_price < price
            tp_valid = tp1_price > price
        else:  # SELL
            sl_valid = sl_price > price
            tp_valid = tp1_price < price

        if not sl_valid:
            logger.warning(
                f"Señal vencida en {symbol} ({direction}) — precio se movió | "
                f"precio_actual={price:.5f} SL={sl_price:.5f} | "
                f"El SL está del lado incorrecto. Señal descartada."
            )
            return None

        if not tp_valid:
            logger.warning(
                f"Señal vencida en {symbol} ({direction}) — precio se movió | "
                f"precio_actual={price:.5f} TP={tp1_price:.5f} | "
                f"El TP está del lado incorrecto. Señal descartada."
            )
            return None

        # ── Validar distancia mínima de stops (trade_stops_level) ────────────
        min_stop_pts = sym_info.trade_stops_level
        min_stop_dist = min_stop_pts * sym_info.point
        sl_dist  = abs(price - sl_price)
        tp_dist  = abs(price - tp1_price)

        if min_stop_dist > 0:
            if sl_dist < min_stop_dist:
                logger.warning(
                    f"SL demasiado cercano en {symbol} | "
                    f"dist={sl_dist:.5f} < mínimo={min_stop_dist:.5f} | Señal descartada"
                )
                return None
            if tp_dist < min_stop_dist:
                logger.warning(
                    f"TP demasiado cercano en {symbol} | "
                    f"dist={tp_dist:.5f} < mínimo={min_stop_dist:.5f} | Señal descartada"
                )
                return None

        # ── #82 Margin Check: verificar margen libre antes de operar ────────────
        # Requiere margen libre ≥ 1.5× el margen requerido para la orden.
        try:
            margin_req = mt5.order_calc_margin(order_type, symbol, lot_size, price)
            acc_info   = mt5.account_info()
            if margin_req and acc_info and margin_req > 0:
                margin_free = acc_info.margin_free
                if margin_free < margin_req * 1.5:
                    logger.warning(
                        f"#82 {symbol}: margen insuficiente — "
                        f"libre=${margin_free:.2f} | requerido=${margin_req:.2f} × 1.5 = "
                        f"${margin_req * 1.5:.2f} — orden descartada"
                    )
                    return None
                logger.debug(
                    f"#82 Margen OK {symbol}: libre=${margin_free:.2f} req=${margin_req:.2f}"
                )
        except Exception as _me82:
            logger.debug(f"#82 margin check error: {_me82}")

        request = {
            "action":    mt5.TRADE_ACTION_DEAL,
            "symbol":    symbol,
            "volume":    round(lot_size, 2),
            "type":      order_type,
            "price":     price,
            "sl":        round(sl_price, sym_info.digits),
            "tp":        round(tp1_price, sym_info.digits),
            "deviation": deviation,
            "magic":     magic,
            "comment":   comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # #30 — Retry Logic: reintentar una vez si el precio se movió levemente
        RETRYABLE_CODES = {10004, 10006, 10007, 10008, 10010, 10011, 10016}
        result = mt5.order_send(request)

        if result is None:
            logger.error(f"order_send() retornó None para {symbol}")
            return None

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            if result.retcode in RETRYABLE_CODES:
                import time as _t
                logger.warning(
                    f"Orden rechazada {symbol} retcode={result.retcode} — "
                    f"reintentando en 3s..."
                )
                _t.sleep(3)
                # Actualizar precio fresco
                tick2 = mt5.symbol_info_tick(symbol)
                if tick2:
                    request["price"] = tick2.ask if direction == "BUY" else tick2.bid
                result = mt5.order_send(request)
                if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                    logger.error(
                        f"Orden rechazada tras reintento {symbol} | "
                        f"retcode={result.retcode if result else 'None'}"
                    )
                    return None
                logger.info(f"Reintento exitoso: {symbol}")
            else:
                logger.error(
                    f"Orden rechazada {symbol} | retcode={result.retcode} | "
                    f"comment={result.comment}"
                )
                return None

        # #75 — Entry Slippage Control: alertar si fill price difiere del precio esperado
        fill_price    = result.price
        slippage_pts  = abs(fill_price - price)
        try:
            from config.instruments import ALL_INSTRUMENTS as _AI
            _instr = _AI.get(symbol)
            _pip   = _instr.pip_size if _instr else 0.0001
            slip_pips = slippage_pts / _pip / 10
            if slip_pips > 2.0:
                logger.warning(
                    f"#75 Slippage elevado en {symbol}: {slip_pips:.1f} pips "
                    f"(esperado={price:.5f} fill={fill_price:.5f})"
                )
        except Exception:
            pass

        logger.info(
            f"Orden ejecutada | {direction} {lot_size} {symbol} @ {fill_price:.5f} | "
            f"SL={sl_price:.5f} TP={tp1_price:.5f} | ticket={result.order}"
        )
        return {
            "ticket":    result.order,
            "symbol":    symbol,
            "direction": direction,
            "lot":       lot_size,
            "price":     fill_price,
            "sl":        sl_price,
            "tp":        tp1_price,
            "retcode":   result.retcode,
        }

    def send_limit_order(
        self,
        symbol: str,
        direction: str,     # "BUY" | "SELL"
        lot_size: float,
        entry_price: float, # precio límite de entrada
        sl_price: float,
        tp1_price: float,
        comment: str = "MQ26v2-LMT",
        magic: int = 26042026,
        expiry_hours: float = 2.0,  # expiración de la orden pendiente
    ) -> Optional[dict]:
        """
        #73 — Smart Limit Order: coloca una orden BUY_LIMIT o SELL_LIMIT en
        `entry_price`. Mejor fill que market order durante el Asian breakout.

        Si `entry_price` ya fue superado (mercado se movió), rechaza la orden
        para evitar fills erróneos.
        """
        if not self._check(): return None

        sym_info = mt5.symbol_info(symbol)
        if sym_info is None:
            logger.error(f"Límit order: símbolo no encontrado: {symbol}")
            return None

        if not sym_info.visible:
            mt5.symbol_select(symbol, True)

        tick  = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        current = tick.ask if direction == "BUY" else tick.bid

        # Validar que el precio límite sea alcanzable (no demasiado lejos)
        if direction == "BUY":
            if entry_price >= current:
                logger.debug(f"#73 {symbol} BUY LIMIT: entry={entry_price:.5f} >= ask={current:.5f} — usar market")
                return None  # Señal de que se debe usar market order
            order_type = mt5.ORDER_TYPE_BUY_LIMIT
        else:
            if entry_price <= current:
                logger.debug(f"#73 {symbol} SELL LIMIT: entry={entry_price:.5f} <= bid={current:.5f} — usar market")
                return None
            order_type = mt5.ORDER_TYPE_SELL_LIMIT

        # #73/#Fix-B — Usar ORDER_TIME_DAY en lugar de ORDER_TIME_SPECIFIED
        # ORDER_TIME_SPECIFIED (retcode=10022) no está soportado en todas las cuentas demo.
        # ORDER_TIME_DAY expira automáticamente al cierre del día del broker (soportado universalmente).
        request = {
            "action":    mt5.TRADE_ACTION_PENDING,
            "symbol":    symbol,
            "volume":    round(lot_size, 2),
            "type":      order_type,
            "price":     round(entry_price, sym_info.digits),
            "sl":        round(sl_price,    sym_info.digits),
            "tp":        round(tp1_price,   sym_info.digits),
            "magic":     magic,
            "comment":   comment,
            "type_time": mt5.ORDER_TIME_DAY,   # expira fin del día del broker
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else "None"
            comment_ = result.comment if result else ""
            logger.warning(f"#73 Limit order rechazada {symbol} retcode={retcode} {comment_}")
            return None

        logger.info(
            f"#73 Limit order colocada | {direction} LIMIT {lot_size} {symbol} @ {entry_price:.5f} | "
            f"SL={sl_price:.5f} TP={tp1_price:.5f} | ticket={result.order} | exp={expiry_hours}h"
        )
        return {
            "ticket":    result.order,
            "symbol":    symbol,
            "direction": direction,
            "lot":       lot_size,
            "price":     entry_price,
            "sl":        sl_price,
            "tp":        tp1_price,
            "retcode":   result.retcode,
            "order_type": "limit",
        }

    def close_position(self, ticket: int) -> bool:
        """Cierra una posición por su ticket."""
        if not self._check(): return False

        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            logger.warning(f"Posición {ticket} no encontrada")
            return False

        p = pos[0]
        direction = "SELL" if p.type == 0 else "BUY"   # inverso para cerrar
        order_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(p.symbol)
        price = tick.bid if direction == "SELL" else tick.ask

        request = {
            "action":    mt5.TRADE_ACTION_DEAL,
            "symbol":    p.symbol,
            "volume":    p.volume,
            "type":      order_type,
            "position":  ticket,
            "price":     price,
            "deviation": 30,
            "magic":     p.magic,
            "comment":   "MQ26v2_close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        if ok:
            logger.info(f"Posición {ticket} cerrada.")
        else:
            logger.error(f"No se pudo cerrar {ticket}: {result}")
        return ok

    # ─── #52 Trailing SL — mover SL a break-even ────────────────────────────

    def modify_sl(self, ticket: int, new_sl: float, new_tp: float = 0.0) -> bool:
        """
        #52 — Modifica el Stop Loss (y opcionalmente el TP) de una posición abierta.

        Args:
            ticket:  Ticket de la posición
            new_sl:  Nuevo nivel de SL (precio absoluto)
            new_tp:  Nuevo TP (0 = no cambiar)
        Returns:
            True si la modificación fue exitosa
        """
        if not self._check(): return False
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            logger.warning(f"modify_sl: posición {ticket} no encontrada")
            return False

        p        = pos[0]
        sym_info = mt5.symbol_info(p.symbol)
        if sym_info is None: return False
        digits   = sym_info.digits

        tp_final = round(new_tp, digits) if new_tp > 0 else p.tp

        request = {
            "action":   mt5.TRADE_ACTION_SLTP,
            "symbol":   p.symbol,
            "position": ticket,
            "sl":       round(new_sl, digits),
            "tp":       tp_final,
            "magic":    p.magic,
        }
        result = mt5.order_send(request)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        if ok:
            logger.info(f"#52 SL modificado | ticket={ticket} nuevo_SL={new_sl:.5f}")
        else:
            err = result.retcode if result else "None"
            logger.warning(f"modify_sl falló | ticket={ticket} retcode={err}")
        return ok

    # ─── #53 Partial Close — cerrar % de la posición ────────────────────────

    def partial_close(self, ticket: int, close_pct: float = 0.5) -> Optional[dict]:
        """
        #53 — Cierra un porcentaje de una posición (por defecto 50%).

        Útil para tomar ganancias parciales en TP1 y dejar correr el resto a TP2.

        Returns:
            dict con close_volume, price si exitoso | None si fallo
        """
        if not self._check(): return None
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            logger.warning(f"partial_close: posición {ticket} no encontrada")
            return None

        p        = pos[0]
        sym_info = mt5.symbol_info(p.symbol)
        if sym_info is None: return None

        vol_step = sym_info.volume_step
        vol_min  = sym_info.volume_min
        target_vol = p.volume * close_pct
        close_vol  = max(vol_min, round(target_vol / vol_step) * vol_step)

        if close_vol >= p.volume:
            logger.debug(f"partial_close: volumen parcial ({close_vol}) ≥ total ({p.volume}) — usando close completo")
            self.close_position(ticket)
            return {"close_volume": p.volume, "full": True}

        direction  = "SELL" if p.type == 0 else "BUY"
        order_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
        tick       = mt5.symbol_info_tick(p.symbol)
        price      = tick.bid if direction == "SELL" else tick.ask

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       p.symbol,
            "volume":       round(close_vol, 2),
            "type":         order_type,
            "position":     ticket,
            "price":        price,
            "deviation":    30,
            "magic":        p.magic,
            "comment":      "MQ26v2_TP1partial",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        if ok:
            logger.info(
                f"#53 Cierre parcial | ticket={ticket} {p.symbol} | "
                f"{close_vol:.2f}/{p.volume:.2f} lotes cerrados @ {price:.5f}"
            )
            return {"close_volume": close_vol, "price": price, "full": False}
        else:
            err = result.retcode if result else "None"
            logger.warning(f"partial_close falló | ticket={ticket} retcode={err}")
            return None

    # ─── #60 Deal History — detectar trades cerrados ─────────────────────────

    def get_closed_deals(self, minutes_back: int = 15) -> list[dict]:
        """
        #60 — Retorna los deals cerrados en los últimos N minutos.
        Usado para detectar cierres automáticos (TP/SL hits).

        Returns:
            Lista de dicts con: ticket, symbol, profit, volume, type, time
        """
        if not self._check(): return []
        import time as _t
        now_ts  = _t.time()
        from_dt = datetime.fromtimestamp(now_ts - minutes_back * 60, tz=timezone.utc)
        to_dt   = datetime.fromtimestamp(now_ts + 10, tz=timezone.utc)

        deals = mt5.history_deals_get(from_dt, to_dt)
        if not deals:
            return []

        result = []
        for d in deals:
            # Solo deals de cierre (entry = DEAL_ENTRY_OUT)
            if d.entry != mt5.DEAL_ENTRY_OUT:
                continue
            if d.magic != 26042026:
                continue
            result.append({
                "ticket":    d.position_id,
                "order":     d.order,
                "symbol":    d.symbol,
                "type":      "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL",
                "volume":    d.volume,
                "price":     d.price,
                "profit":    d.profit,
                "swap":      d.swap,
                "time":      datetime.fromtimestamp(d.time, tz=timezone.utc),
                "comment":   d.comment,
            })
        return result

    # ─── Posiciones abiertas ─────────────────────────────────────────────────

    def get_open_positions(self) -> list[dict]:
        """Retorna todas las posiciones abiertas del magic number del bot."""
        if not self._check(): return []
        positions = mt5.positions_get(magic=26042026)
        if not positions: return []
        result = []
        for p in positions:
            result.append({
                "ticket":    p.ticket,
                "symbol":    p.symbol,
                "direction": "BUY" if p.type == 0 else "SELL",
                "volume":    p.volume,
                "open_price": p.price_open,
                "sl":        p.sl,
                "tp":        p.tp,
                "profit":    p.profit,
                "open_time": datetime.fromtimestamp(p.time, tz=timezone.utc),
            })
        return result

    def get_portfolio_summary(self) -> dict:
        """Resumen del portafolio en tiempo real."""
        acc  = self.get_account_info() or {}
        pos  = self.get_open_positions()
        return {
            "account":   acc,
            "positions": pos,
            "n_open":    len(pos),
            "total_profit": sum(p["profit"] for p in pos),
        }

    # ─── Kill switch ─────────────────────────────────────────────────────────

    def kill_switch(self) -> int:
        """Cierra TODAS las posiciones abiertas del bot. Retorna cantidad cerradas."""
        if not self._check(): return 0
        positions = self.get_open_positions()
        closed = 0
        for p in positions:
            if self.close_position(p["ticket"]):
                closed += 1
        logger.warning(f"KILL SWITCH ejecutado — {closed} posiciones cerradas.")
        return closed

    # ─── Internos ────────────────────────────────────────────────────────────

    def _check(self) -> bool:
        if not MT5_AVAILABLE:
            return False
        if not self._connected:
            logger.warning("MT5 no conectado. Llamar connect() primero.")
            return False
        return True

    def _get_pip_size(self, symbol: str) -> float:
        info = mt5.symbol_info(symbol)
        if info is None:
            return 0.0001
        return info.point * 10 if "JPY" not in symbol else info.point * 10

    def _resolve_timeframe(self, tf: str) -> int:
        if not MT5_AVAILABLE:
            return 5
        mapping = {
            "M1":  mt5.TIMEFRAME_M1,
            "M5":  mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1":  mt5.TIMEFRAME_H1,
            "H4":  mt5.TIMEFRAME_H4,
            "D1":  mt5.TIMEFRAME_D1,
        }
        return mapping.get(tf.upper(), mt5.TIMEFRAME_M5)


# Singleton para uso global
_connector: Optional[MT5Connector] = None

def get_connector() -> MT5Connector:
    global _connector
    if _connector is None:
        _connector = MT5Connector()
    return _connector
