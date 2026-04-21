"""
MQ26 BOT v2 — Dashboard de Comando

Tablero institucional con panel Live MT5 + análisis de backtest.

Uso:
    cd MQ26_BOT_v2
    streamlit run dashboard.py --server.port 8503
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

REPORT_DIR = Path(__file__).resolve().parent / "data" / "reports"
TRADES_CSV = REPORT_DIR / "backtest_report_trades.csv"

# ── Paleta ────────────────────────────────────────────────────────────────────
GREEN  = "#00C896"
RED    = "#FF4B4B"
BLUE   = "#4B9FFF"
YELLOW = "#FFD166"
GRAY   = "#888888"
BG     = "#0E1117"
CARD   = "#1A1D2E"

STRATEGY_COLORS = {
    "S03_AsianRange": "#00C896",   # ← Producción: verde
    "S01_LondonKZ":   "#4B9FFF",   # Experimental
    "S02_FVGRetest":  "#FFD166",   # Experimental
}

# Estrategias descartadas — PF < 1, Sharpe negativo
# Se excluyen del dashboard por defecto para no confundir métricas
EXCLUDED_STRATEGIES = {"S06_OBLondon", "S07_OBLondon"}

PAIRS_LIVE = [
    "BTCUSD", "XAUUSD", "AUDUSD", "NZDUSD",
    "ETHUSD", "GBPUSD", "EURUSD", "AUDJPY",
]  # Top 8 — S03v3 (60d M5) todos con PF > 1

# Símbolo MT5 → nombre legible y clase
SYMBOL_META = {
    "BTCUSD": ("Bitcoin / USD",    "crypto", "24/7"),
    "XAUUSD": ("Oro / USD",        "gold",   "Lun–Vie"),
    "AUDUSD": ("Aussie / USD",     "forex",  "Lun–Vie"),
    "NZDUSD": ("NZD / USD",        "forex",  "Lun–Vie"),
    "ETHUSD": ("Ethereum / USD",   "crypto", "24/7"),
    "GBPUSD": ("Pound / USD",      "forex",  "Lun–Vie"),
    "EURUSD": ("Euro / USD",       "forex",  "Lun–Vie"),
    "AUDJPY": ("Aussie / Yen",     "forex",  "Lun–Vie"),
}

LOG_FILE = Path(__file__).resolve().parent / "data" / "logs" / "demo_trader.log"


def is_market_open_now(symbol: str) -> bool:
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    if symbol == "BTCUSD":
        return True
    wd, h = now.weekday(), now.hour
    if wd == 5: return False
    if wd == 6 and h < 22: return False
    if wd == 4 and h >= 22: return False
    return True


def load_recent_signals(max_lines: int = 200) -> list[dict]:
    """Lee el log del demo_trader y extrae las últimas señales."""
    if not LOG_FILE.exists():
        return []
    signals = []
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-max_lines:]):
            if "SEÑAL" not in line and "SENAL" not in line and "SE\u00d1AL" not in line:
                continue
            # Formato: "HH:MM:SS | INFO | demo_trader — SEÑAL LONG | BTCUSD [crypto] | ..."
            parts = line.split(" — ", 1)
            timestamp_raw = parts[0].split("|")[0].strip()
            body = parts[1] if len(parts) > 1 else line
            tokens = [t.strip() for t in body.split("|")]
            # tokens[0]="SEÑAL LONG", tokens[1]="BTCUSD [crypto]", tokens[2]="Entry=…"
            direction = tokens[0].replace("SEÑAL","").replace("SENAL","").strip() if tokens else "?"
            symbol_raw = tokens[1].split("[")[0].strip() if len(tokens) > 1 else "?"
            entry_tok = next((t for t in tokens if "Entry=" in t), "")
            sl_tok    = next((t for t in tokens if "SL=" in t), "")
            tp1_tok   = next((t for t in tokens if "TP1=" in t), "")
            rr_tok    = next((t for t in tokens if "R:R=" in t), "")
            notes_tok = tokens[-1] if len(tokens) > 4 else ""

            def _extract(tok, key):
                try:
                    return float(tok.split(key)[1].split()[0].split("|")[0])
                except Exception:
                    return None

            signals.append({
                "time":      timestamp_raw,
                "symbol":    symbol_raw,
                "direction": direction,
                "entry":     _extract(entry_tok, "Entry="),
                "sl":        _extract(sl_tok, "SL="),
                "tp1":       _extract(tp1_tok, "TP1="),
                "rr":        _extract(rr_tok, "R:R="),
                "notes":     notes_tok,
            })
        signals.reverse()
    except Exception:
        pass
    return signals[-20:]   # últimas 20

# ── Página ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MQ26 BOT v2",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding: 1.5rem 2rem 1rem; }
    .metric-card {
        background: #1A1D2E; border-radius: 10px;
        padding: 1rem 1.2rem; border-left: 4px solid #4B9FFF;
        margin-bottom: 0.5rem;
    }
    .metric-card.green  { border-left-color: #00C896; }
    .metric-card.red    { border-left-color: #FF4B4B; }
    .metric-card.yellow { border-left-color: #FFD166; }
    .kpi-value { font-size: 2rem; font-weight: 700; color: #FFFFFF; margin: 0; }
    .kpi-label { font-size: 0.75rem; color: #AECBFF; text-transform: uppercase; letter-spacing: 1px; }
    .kpi-delta { font-size: 0.85rem; margin-top: 0.2rem; }
    .section-title {
        font-size: 1.1rem; font-weight: 600; color: #FFFFFF;
        border-bottom: 1px solid #2A2D3E;
        padding-bottom: 0.5rem; margin: 1.5rem 0 1rem;
    }
    .live-dot { display:inline-block; width:10px; height:10px;
        background:#FF4B4B; border-radius:50%; margin-right:6px;
        animation: blink 1s infinite; }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }
    ::-webkit-scrollbar { width:6px; height:6px; }
    ::-webkit-scrollbar-track { background:#0E1117; }
    ::-webkit-scrollbar-thumb { background:#3A3D5E; border-radius:3px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# MT5 — conexión compartida en sesión
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def _get_connector():
    from execution.mt5_connector import MT5Connector
    conn = MT5Connector()
    conn.connect()
    return conn


def get_live_data() -> dict:
    """Obtiene datos en vivo de MT5. Retorna dict vacío si no disponible."""
    try:
        conn = _get_connector()
        if not conn.is_connected():
            conn.reconnect()

        acc       = conn.get_account_info() or {}
        positions = conn.get_open_positions()
        ticks     = {}
        for sym in PAIRS_LIVE:
            t = conn.get_tick(sym)
            if t:
                ticks[sym] = t

        return {"account": acc, "positions": positions, "ticks": ticks, "ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Backtest — carga de datos
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_trades() -> pd.DataFrame:
    if not TRADES_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(TRADES_CSV, parse_dates=["open_time", "close_time"])
    df["open_time"]  = pd.to_datetime(df["open_time"],  utc=True, errors="coerce")
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True, errors="coerce")
    df["is_winner"]  = df["pnl_pips"] > 0
    df["open_date"]  = df["open_time"].dt.date
    df["hour_open"]  = df["open_time"].dt.hour
    df["session"]    = df["hour_open"].map(_classify_session)
    return df


def _classify_session(hour: int) -> str:
    if 0  <= hour < 7:  return "Tokyo"
    if 7  <= hour < 12: return "London"
    if 12 <= hour < 16: return "Overlap"
    if 16 <= hour < 21: return "New York"
    return "Off"


def compute_equity_curve(df: pd.DataFrame, initial: float = 10_000) -> pd.Series:
    if df.empty:
        return pd.Series([initial])
    s = df.sort_values("open_time").copy()
    s["cumulative_pnl"] = s["pnl_usd"].cumsum()
    eq = initial + s["cumulative_pnl"]
    eq.index = s["open_time"].values
    return eq


def compute_kpis(df: pd.DataFrame, initial: float = 10_000) -> dict:
    if df.empty:
        return {}
    closed = df[df["outcome"] != "open"].copy()
    if closed.empty:
        return {}
    winners = closed[closed["is_winner"]]
    losers  = closed[~closed["is_winner"]]
    gross_profit = winners["pnl_usd"].sum()
    gross_loss   = abs(losers["pnl_usd"].sum())
    total_pnl    = closed["pnl_usd"].sum()
    equity       = compute_equity_curve(closed, initial)
    peak         = equity.expanding().max()
    dd_pct       = ((peak - equity) / peak * 100).max()
    daily        = closed.groupby("open_date")["pnl_usd"].sum()
    sharpe       = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0
    return {
        "total_trades":   len(closed),
        "winning_trades": len(winners),
        "losing_trades":  len(losers),
        "win_rate":       len(winners) / len(closed),
        "profit_factor":  gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "total_pnl_usd":  total_pnl,
        "total_pnl_pct":  total_pnl / initial * 100,
        "final_equity":   initial + total_pnl,
        "max_dd_pct":     dd_pct,
        "sharpe":         sharpe,
        "avg_win_pips":   winners["pnl_pips"].mean() if not winners.empty else 0,
        "avg_loss_pips":  abs(losers["pnl_pips"].mean()) if not losers.empty else 0,
        "avg_duration_h": closed["duration_h"].mean(),
    }


def kpi_card(col, label, value, delta="", color=BLUE):
    border = {GREEN: "green", RED: "red", YELLOW: "yellow"}.get(color, "")
    col.markdown(f"""
        <div class="metric-card {border}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-delta" style="color:{color}">{delta}</div>
        </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Controles")
    st.markdown("---")

    # Auto-refresh para live
    auto_refresh = st.toggle("Auto-refresh Live (10s)", value=False)
    refresh_sec  = st.slider("Intervalo refresh (s)", 5, 60, 10, disabled=not auto_refresh)

    st.markdown("---")
    st.markdown("## 📊 Filtros Backtest")

    df_all = load_trades()
    if not df_all.empty:
        # Estrategias disponibles — excluir las descartadas del listado
        available_strats = sorted(
            s for s in df_all["strategy"].unique()
            if s not in EXCLUDED_STRATEGIES
        )
        strategy_opts = ["S03 (producción)"] + available_strats + ["— Ver todo —"]
        sel_strat = st.selectbox(
            "Estrategia",
            strategy_opts,
            index=0,   # Default: S03 producción
            help="S06_OBLondon excluido (PF 0.54, Sharpe -6.97 — descartado)"
        )

        # Resolver el filtro real
        if sel_strat == "S03 (producción)":
            _strat_filter = "S03_AsianRange"
        elif sel_strat == "— Ver todo —":
            _strat_filter = "Todas"
        else:
            _strat_filter = sel_strat

        symbols    = ["Todos"] + sorted(df_all["symbol"].unique().tolist())
        sel_symbol = st.selectbox("Par / Instrumento", symbols)
        outcomes   = ["Todos", "tp1", "tp2", "sl", "be", "manual"]
        sel_out    = st.selectbox("Resultado", outcomes)
        st.markdown("---")
        initial_capital = st.number_input("Capital inicial (USD)", value=2_000, step=500)
    else:
        _strat_filter = "S03_AsianRange"; sel_symbol = "Todos"; sel_out = "Todos"
        initial_capital = 2_000

    st.markdown("---")
    if st.button("🔄 Recargar datos", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.caption("MQ26 BOT v2 | IC Markets MT5 Demo")


# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 8])
with col_logo:
    st.markdown("# 📈")
with col_title:
    st.markdown("# MQ26 BOT v2 — Dashboard de Comando")
    st.caption("Forex · Índices · Oro | IC Markets MT5 | Estrategias institucionales")

st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# TABS principales
# ─────────────────────────────────────────────────────────────────────────────
tab_live, tab_backtest, tab_margin = st.tabs([
    "🔴  Live MT5",
    "📊  Backtest Analysis",
    "📐  Calculadora Márgenes",
])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — LIVE MT5
# ═════════════════════════════════════════════════════════════════════════════
with tab_live:

    live = get_live_data()

    if not live.get("ok"):
        st.error(f"MT5 no disponible: {live.get('error', 'Sin conexión')}")
        st.info("Abrí MetaTrader 5 y logueate a la cuenta demo, luego recargá.")
    else:
        acc       = live["account"]
        positions = live["positions"]
        ticks     = live["ticks"]

        # ── Timestamp ───────────────────────────────────────────────────────
        import datetime as dt
        now_utc = dt.datetime.now(dt.timezone.utc)
        now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        st.markdown(
            f'<span class="live-dot"></span>'
            f'<span style="color:#AECBFF;font-size:0.85rem">Conectado — {now_str}</span>',
            unsafe_allow_html=True,
        )

        # ── Estado de mercados (Top 8) ───────────────────────────────────────
        st.markdown('<div class="section-title">🌐 Top 8 — Estado de Mercados (S03v3)</div>',
                    unsafe_allow_html=True)
        mkt_cols = st.columns(len(PAIRS_LIVE))
        for col_m, sym in zip(mkt_cols, PAIRS_LIVE):
            meta = SYMBOL_META.get(sym, (sym, "?", "?"))
            is_open = is_market_open_now(sym)
            dot   = "🟢" if is_open else "🔴"
            label = "ABIERTO" if is_open else "CERRADO"
            color = GREEN if is_open else GRAY
            col_m.markdown(f"""
                <div class="metric-card {'green' if is_open else ''}">
                    <div class="kpi-label">{sym}</div>
                    <div style="font-size:1.4rem">{dot}</div>
                    <div style="font-size:0.8rem;color:{color};font-weight:600">{label}</div>
                    <div style="font-size:0.7rem;color:#888">{meta[2]}</div>
                </div>
            """, unsafe_allow_html=True)

        # ── KPIs de cuenta ──────────────────────────────────────────────────
        st.markdown('<div class="section-title">💼 Estado de Cuenta MT5</div>',
                    unsafe_allow_html=True)

        balance    = acc.get("balance", 0)
        equity     = acc.get("equity", 0)
        margin     = acc.get("margin", 0)
        free_m     = acc.get("free_margin", 0)
        profit     = acc.get("profit", 0)
        leverage   = acc.get("leverage", 0)
        dd_from_balance = ((balance - equity) / balance * 100) if balance > 0 else 0

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        kpi_card(c1, "Balance",      f"${balance:,.2f}",  acc.get("currency","USD"), BLUE)
        kpi_card(c2, "Equity",       f"${equity:,.2f}",
                 f"{'↑' if equity >= balance else '↓'} vs balance",
                 GREEN if equity >= balance else RED)
        kpi_card(c3, "P&L Abierto",  f"{'+'if profit>=0 else ''}{profit:,.2f}",
                 "posiciones abiertas", GREEN if profit >= 0 else RED)
        kpi_card(c4, "Margen Usado", f"${margin:,.2f}",   f"Libre: ${free_m:,.2f}", YELLOW)
        kpi_card(c5, "DD vs Balance",f"{dd_from_balance:.2f}%",
                 "< 5% objetivo", GREEN if dd_from_balance < 5 else (YELLOW if dd_from_balance < 10 else RED))
        kpi_card(c6, "Leverage",     f"1:{leverage}",     f"{acc.get('server','')}", BLUE)

        # ── Precios en tiempo real ───────────────────────────────────────────
        st.markdown('<div class="section-title">💹 Precios en Tiempo Real</div>',
                    unsafe_allow_html=True)

        if ticks:
            tick_headers = ["Par", "Bid", "Ask", "Spread (pips)", "Hora (UTC)"]
            tick_syms  = list(ticks.keys())
            tick_bids  = [f"{ticks[s]['bid']:.5f}" for s in tick_syms]
            tick_asks  = [f"{ticks[s]['ask']:.5f}" for s in tick_syms]
            tick_sprd  = [f"{ticks[s]['spread']:.1f}" for s in tick_syms]
            tick_times = [ticks[s]['time'].strftime("%H:%M:%S") for s in tick_syms]

            spread_colors = [
                GREEN if ticks[s]["spread"] <= 2 else
                (YELLOW if ticks[s]["spread"] <= 5 else RED)
                for s in tick_syms
            ]

            fig_ticks = go.Figure(go.Table(
                columnwidth=[90, 100, 100, 120, 100],
                header=dict(
                    values=[f"<b>{h}</b>" for h in tick_headers],
                    fill_color="#12152B",
                    font=dict(color="#FFFFFF", size=12, family="Consolas, monospace"),
                    align="center", height=32, line_color="#2A2D3E",
                ),
                cells=dict(
                    values=[tick_syms, tick_bids, tick_asks, tick_sprd, tick_times],
                    fill_color="#1A1D2E",
                    font=dict(
                        color=[
                            ["#4B9FFF"] * len(tick_syms),
                            ["#FFFFFF"] * len(tick_syms),
                            ["#FFFFFF"] * len(tick_syms),
                            spread_colors,
                            ["#888888"] * len(tick_syms),
                        ],
                        size=12, family="Consolas, monospace",
                    ),
                    align="center", height=28, line_color="#2A2D3E",
                ),
            ))
            fig_ticks.update_layout(
                template="plotly_dark",
                margin=dict(l=0, r=0, t=0, b=0),
                height=50 + 30 * len(tick_syms),
                paper_bgcolor="#0E1117",
            )
            st.plotly_chart(fig_ticks, use_container_width=True)
        else:
            st.warning("Sin ticks disponibles — verificá que los símbolos estén en el Market Watch de MT5.")

        # ── Posiciones abiertas ──────────────────────────────────────────────
        st.markdown('<div class="section-title">📂 Posiciones Abiertas</div>',
                    unsafe_allow_html=True)

        if positions:
            pos_headers = ["Ticket", "Par", "Dir", "Volumen", "Precio Entrada",
                           "SL", "TP", "P&L ($)", "Apertura (UTC)"]
            tickets    = [p["ticket"]    for p in positions]
            syms_p     = [p["symbol"]    for p in positions]
            dirs_p     = [p["direction"] for p in positions]
            vols       = [p["volume"]    for p in positions]
            entries    = [f"{p['open_price']:.5f}" for p in positions]
            sls        = [f"{p['sl']:.5f}"         for p in positions]
            tps        = [f"{p['tp']:.5f}"         for p in positions]
            profits    = [f"{'+'if p['profit']>=0 else ''}{p['profit']:.2f}" for p in positions]
            times_p    = [p["open_time"].strftime("%m-%d %H:%M") for p in positions]

            pnl_colors = [GREEN if p["profit"] >= 0 else RED for p in positions]
            dir_colors = [GREEN if d == "BUY" else RED for d in dirs_p]

            fig_pos = go.Figure(go.Table(
                columnwidth=[80, 80, 55, 75, 120, 110, 110, 90, 110],
                header=dict(
                    values=[f"<b>{h}</b>" for h in pos_headers],
                    fill_color="#12152B",
                    font=dict(color="#FFFFFF", size=11, family="Consolas, monospace"),
                    align="center", height=32, line_color="#2A2D3E",
                ),
                cells=dict(
                    values=[tickets, syms_p, dirs_p, vols, entries, sls, tps, profits, times_p],
                    fill_color="#1A1D2E",
                    font=dict(
                        color=[
                            ["#888888"] * len(positions),
                            ["#4B9FFF"] * len(positions),
                            dir_colors,
                            ["#FFFFFF"] * len(positions),
                            ["#FFFFFF"] * len(positions),
                            [RED]       * len(positions),
                            [GREEN]     * len(positions),
                            pnl_colors,
                            ["#888888"] * len(positions),
                        ],
                        size=12, family="Consolas, monospace",
                    ),
                    align="center", height=28, line_color="#2A2D3E",
                ),
            ))
            fig_pos.update_layout(
                template="plotly_dark",
                margin=dict(l=0, r=0, t=0, b=0),
                height=50 + 30 * len(positions),
                paper_bgcolor="#0E1117",
            )
            st.plotly_chart(fig_pos, use_container_width=True)

            total_pnl_live = sum(p["profit"] for p in positions)
            st.markdown(
                f"**P&L total abierto:** "
                f"<span style='color:{'#00C896' if total_pnl_live >= 0 else '#FF4B4B'};font-size:1.1rem;font-weight:700'>"
                f"{'+'if total_pnl_live>=0 else ''}{total_pnl_live:.2f} USD</span>",
                unsafe_allow_html=True,
            )
        else:
            st.info("Sin posiciones abiertas en este momento.")

        # ── Señales Recientes del Demo Trader ───────────────────────────────
        st.markdown('<div class="section-title">📡 Señales Recientes — Demo Trader</div>',
                    unsafe_allow_html=True)

        recent_sigs = load_recent_signals()
        if not recent_sigs:
            st.info("Sin señales aún. Corré: `python demo_trader.py --dry-run`")
        else:
            sig_headers = ["Hora", "Símbolo", "Dirección", "Entry", "SL", "TP1", "R:R", "Notas"]
            sig_times  = [s["time"]      for s in recent_sigs]
            sig_syms   = [s["symbol"]    for s in recent_sigs]
            sig_dirs   = [s["direction"] for s in recent_sigs]
            sig_ents   = [f"{s['entry']:.2f}"  if s["entry"] else "—" for s in recent_sigs]
            sig_sls    = [f"{s['sl']:.2f}"     if s["sl"]    else "—" for s in recent_sigs]
            sig_tp1s   = [f"{s['tp1']:.2f}"    if s["tp1"]   else "—" for s in recent_sigs]
            sig_rrs    = [f"{s['rr']:.2f}"     if s["rr"]    else "—" for s in recent_sigs]
            sig_notes  = [s["notes"][:60]      for s in recent_sigs]

            dir_clrs = [GREEN if "LONG" in d else RED for d in sig_dirs]

            fig_sigs = go.Figure(go.Table(
                columnwidth=[80, 80, 70, 100, 100, 100, 55, 300],
                header=dict(
                    values=[f"<b>{h}</b>" for h in sig_headers],
                    fill_color="#12152B",
                    font=dict(color="#FFFFFF", size=11, family="Consolas, monospace"),
                    align="center", height=30, line_color="#2A2D3E",
                ),
                cells=dict(
                    values=[sig_times, sig_syms, sig_dirs, sig_ents,
                            sig_sls, sig_tp1s, sig_rrs, sig_notes],
                    fill_color="#1A1D2E",
                    font=dict(
                        color=[
                            ["#888888"] * len(recent_sigs),
                            ["#4B9FFF"] * len(recent_sigs),
                            dir_clrs,
                            ["#FFFFFF"] * len(recent_sigs),
                            [RED]       * len(recent_sigs),
                            [GREEN]     * len(recent_sigs),
                            ["#FFD166"] * len(recent_sigs),
                            ["#AAAAAA"] * len(recent_sigs),
                        ],
                        size=11, family="Consolas, monospace",
                    ),
                    align=["center","center","center","right","right","right","center","left"],
                    height=26, line_color="#2A2D3E",
                ),
            ))
            fig_sigs.update_layout(
                template="plotly_dark",
                margin=dict(l=0, r=0, t=0, b=0),
                height=50 + 28 * len(recent_sigs),
                paper_bgcolor="#0E1117",
            )
            st.plotly_chart(fig_sigs, use_container_width=True)
            st.caption(f"Log: `{LOG_FILE}` — últimas 20 señales detectadas")

        # ── Kill Switch ──────────────────────────────────────────────────────
        st.markdown('<div class="section-title">🛑 Control de Emergencia</div>',
                    unsafe_allow_html=True)

        col_ks1, col_ks2, col_ks3 = st.columns([1, 1, 4])

        with col_ks1:
            kill_pressed = st.button(
                "🛑 KILL SWITCH",
                type="primary",
                width="stretch",
                help="Cierra TODAS las posiciones abiertas inmediatamente",
            )

        with col_ks2:
            confirm_pressed = st.button(
                "✅ CONFIRMAR",
                width="stretch",
                help="Confirmar el kill switch",
            )

        with col_ks3:
            if positions:
                st.warning(
                    f"⚠️ Hay **{len(positions)} posición(es) abierta(s)**. "
                    "Presioná KILL SWITCH y luego CONFIRMAR para cerrarlas todas."
                )
            else:
                st.success("Sin posiciones abiertas — kill switch no necesario.")

        if "ks_pending" not in st.session_state:
            st.session_state.ks_pending = False

        if kill_pressed:
            st.session_state.ks_pending = True
            st.warning("Kill switch preparado. Presioná CONFIRMAR para ejecutar.")

        if confirm_pressed and st.session_state.ks_pending:
            try:
                conn = _get_connector()
                closed = conn.kill_switch()
                st.session_state.ks_pending = False
                st.success(f"Kill switch ejecutado — {closed} posición(es) cerrada(s).")
                st.balloons()
            except Exception as e:
                st.error(f"Error en kill switch: {e}")

        # ── Auto-refresh ─────────────────────────────────────────────────────
        if auto_refresh:
            time.sleep(refresh_sec)
            st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — BACKTEST ANALYSIS
# ═════════════════════════════════════════════════════════════════════════════
with tab_backtest:

    df_all = load_trades()
    if df_all.empty:
        st.warning("Sin datos de backtest. Corré primero:")
        st.code("python main_backtest.py --strategy s03 --period 60d")
        st.stop()

    # Banner informativo — estrategia de producción
    st.markdown("""
    <div style="background:#0D2B1A;border-left:4px solid #00C896;padding:0.8rem 1.2rem;
                border-radius:6px;margin-bottom:1rem">
        <span style="color:#00C896;font-weight:700;font-size:0.95rem">
            ✅ ESTRATEGIA DE PRODUCCIÓN: S03 Asian Range v3
        </span><br>
        <span style="color:#AECBFF;font-size:0.82rem">
            Top 8 pares validados · 60d M5 · Todos PF > 1 · Sharpe 8–26
            &nbsp;|&nbsp;
            S06 OBLondon excluido (PF 0.54, Sharpe −6.97)
        </span>
    </div>
    """, unsafe_allow_html=True)

    # Siempre excluir estrategias descartadas del análisis agregado
    df = df_all[~df_all["strategy"].isin(EXCLUDED_STRATEGIES)].copy()

    if _strat_filter != "Todas": df = df[df["strategy"] == _strat_filter]
    if sel_symbol    != "Todos": df = df[df["symbol"]   == sel_symbol]
    if sel_out       != "Todos": df = df[df["outcome"]  == sel_out]

    kpis = compute_kpis(df, initial_capital)

    if not kpis:
        st.warning("Sin trades con los filtros seleccionados.")
        st.stop()

    # ── KPIs principales ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">📊 KPIs Principales</div>', unsafe_allow_html=True)
    pnl_sign  = "+" if kpis["total_pnl_pct"] >= 0 else ""
    pnl_color = GREEN if kpis["total_pnl_pct"] >= 0 else RED
    dd_color  = GREEN if kpis["max_dd_pct"] < 10 else (YELLOW if kpis["max_dd_pct"] < 20 else RED)
    wr_color  = GREEN if kpis["win_rate"] > 0.45 else (YELLOW if kpis["win_rate"] > 0.35 else RED)
    pf_color  = GREEN if kpis["profit_factor"] > 1.5 else (YELLOW if kpis["profit_factor"] > 1.0 else RED)
    sh_color  = GREEN if kpis["sharpe"] > 1 else (YELLOW if kpis["sharpe"] > 0 else RED)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    kpi_card(c1, "PnL Total",     f"{pnl_sign}${kpis['total_pnl_usd']:,.0f}",
             f"{pnl_sign}{kpis['total_pnl_pct']:.2f}%", pnl_color)
    kpi_card(c2, "Win Rate",      f"{kpis['win_rate']:.1%}",
             f"{kpis['winning_trades']}W / {kpis['losing_trades']}L", wr_color)
    kpi_card(c3, "Profit Factor", f"{kpis['profit_factor']:.2f}" if kpis['profit_factor'] != float('inf') else "inf",
             "", pf_color)
    kpi_card(c4, "Sharpe Ratio",  f"{kpis['sharpe']:.2f}", "> 1 = bueno", sh_color)
    kpi_card(c5, "Max Drawdown",  f"{kpis['max_dd_pct']:.1f}%", "< 10% objetivo", dd_color)
    kpi_card(c6, "Trades Totales",str(kpis["total_trades"]),
             f"Avg {kpis['avg_duration_h']:.1f}h", BLUE)

    st.markdown("")
    c1b, c2b, c3b, c4b = st.columns(4)
    with c1b:
        st.metric("Capital Final", f"${kpis['final_equity']:,.2f}",
                  f"{pnl_sign}{kpis['total_pnl_pct']:.2f}%",
                  delta_color="normal" if kpis["total_pnl_pct"] >= 0 else "inverse")
    with c2b:
        st.metric("Avg Win", f"{kpis['avg_win_pips']:.1f} pips")
    with c3b:
        st.metric("Avg Loss", f"{kpis['avg_loss_pips']:.1f} pips")
    with c4b:
        rr = kpis["avg_win_pips"] / kpis["avg_loss_pips"] if kpis["avg_loss_pips"] > 0 else 0
        st.metric("R:R Real", f"1 : {rr:.2f}")

    # ── Curvas de equity ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">📊 Curva de Equity por Estrategia</div>',
                unsafe_allow_html=True)

    fig_eq = go.Figure()
    fig_eq.add_hline(y=initial_capital, line_dash="dot", line_color=GRAY,
                     annotation_text="Capital inicial", annotation_position="right")

    for (strat, sym), grp in df.groupby(["strategy", "symbol"]):
        g = grp.sort_values("open_time")
        eq = initial_capital + g["pnl_usd"].cumsum().values
        color = STRATEGY_COLORS.get(strat, BLUE)
        pnl_f = eq[-1] - initial_capital if len(eq) else 0
        sign  = "+" if pnl_f >= 0 else ""
        fig_eq.add_trace(go.Scatter(
            x=g["open_time"].values, y=eq, mode="lines",
            name=f"{strat} | {sym}  ({sign}${pnl_f:,.0f})",
            line=dict(color=color, width=2),
            hovertemplate=f"<b>{strat} {sym}</b><br>%{{x|%Y-%m-%d %H:%M}}<br>Equity: $%{{y:,.2f}}<extra></extra>",
        ))

    fig_eq.update_layout(
        template="plotly_dark", height=360,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
        yaxis_title="Equity (USD)", xaxis_title="",
        paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(family="Consolas, monospace", size=11),
    )
    st.plotly_chart(fig_eq, use_container_width=True)

    # ── PnL por trade + Outcomes ────────────────────────────────────────────
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.markdown('<div class="section-title">📉 PnL por Trade (pips)</div>', unsafe_allow_html=True)
        ds = df.sort_values("open_time").reset_index(drop=True)
        fig_bars = go.Figure(go.Bar(
            x=list(range(len(ds))),
            y=ds["pnl_pips"],
            marker_color=[GREEN if p > 0 else RED for p in ds["pnl_pips"]],
            hovertext=[
                f"Trade #{i+1}<br>{r['strategy']} | {r['symbol']}<br>"
                f"PnL: {r['pnl_pips']:.1f} pips (${r['pnl_usd']:.2f})<br>{r['notes']}"
                for i, r in ds.iterrows()
            ],
            hoverinfo="text",
        ))
        fig_bars.add_hline(y=0, line_color=GRAY, line_dash="dot")
        fig_bars.update_layout(
            template="plotly_dark", height=260,
            margin=dict(l=0, r=0, t=5, b=0),
            paper_bgcolor=CARD, plot_bgcolor=CARD,
            xaxis_title="Trades", yaxis_title="Pips",
            font=dict(family="Consolas, monospace", size=11),
        )
        st.plotly_chart(fig_bars, use_container_width=True)

    with col_right:
        st.markdown('<div class="section-title">🎯 Resultados por Outcome</div>', unsafe_allow_html=True)
        oc = df["outcome"].value_counts().reset_index()
        oc.columns = ["outcome", "count"]
        oc_map = {"tp2": GREEN, "tp1": "#00A87C", "be": YELLOW, "sl": RED, "manual": GRAY}
        fig_pie = go.Figure(go.Pie(
            labels=oc["outcome"], values=oc["count"],
            marker_colors=[oc_map.get(o, BLUE) for o in oc["outcome"]],
            hole=0.55, textinfo="label+percent",
            hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
        ))
        fig_pie.update_layout(
            template="plotly_dark", height=260,
            margin=dict(l=0, r=0, t=5, b=0),
            paper_bgcolor=CARD, plot_bgcolor=CARD,
            showlegend=False,
            font=dict(family="Consolas, monospace", size=11),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    # ── Sesión + Heatmap ────────────────────────────────────────────────────
    col_sess, col_heat = st.columns(2)

    with col_sess:
        st.markdown('<div class="section-title">🌍 Performance por Sesión</div>', unsafe_allow_html=True)
        ss = df.groupby("session").agg(
            trades=("pnl_pips","count"), total_pips=("pnl_pips","sum"),
            win_rate=("is_winner","mean"),
        ).reset_index()
        ss["win_rate_pct"] = (ss["win_rate"] * 100).round(1)
        ss["total_pips"]   = ss["total_pips"].round(1)
        fig_sess = go.Figure()
        fig_sess.add_trace(go.Bar(
            x=ss["session"], y=ss["total_pips"],
            marker_color=[GREEN if v > 0 else RED for v in ss["total_pips"]],
            name="PnL total (pips)",
            hovertemplate="%{x}<br>PnL: %{y:.1f} pips<extra></extra>",
        ))
        fig_sess.add_trace(go.Scatter(
            x=ss["session"], y=ss["win_rate_pct"],
            mode="lines+markers", name="Win Rate %", yaxis="y2",
            line=dict(color=YELLOW, width=2), marker=dict(size=8),
            hovertemplate="%{x}<br>Win Rate: %{y:.1f}%<extra></extra>",
        ))
        fig_sess.update_layout(
            template="plotly_dark", height=280,
            margin=dict(l=0, r=0, t=5, b=0),
            paper_bgcolor=CARD, plot_bgcolor=CARD,
            legend=dict(orientation="h", y=1.05),
            yaxis=dict(title="PnL (pips)"),
            yaxis2=dict(title="Win Rate %", overlaying="y", side="right", range=[0,100]),
            font=dict(family="Consolas, monospace", size=11),
        )
        st.plotly_chart(fig_sess, use_container_width=True)

    with col_heat:
        st.markdown('<div class="section-title">⏰ PnL Promedio por Hora</div>', unsafe_allow_html=True)
        hp = df.groupby("hour_open")["pnl_pips"].agg(["mean","count"]).reset_index()
        fig_heat = go.Figure(go.Bar(
            x=[f"{h:02d}:00" for h in hp["hour_open"]],
            y=hp["mean"],
            marker_color=[GREEN if v > 0 else RED for v in hp["mean"]],
            text=[f"n={c}" for c in hp["count"]],
            textposition="outside",
            hovertemplate="Hora: %{x}<br>Avg PnL: %{y:.1f} pips<extra></extra>",
        ))
        fig_heat.add_hline(y=0, line_color=GRAY, line_dash="dot")
        fig_heat.update_layout(
            template="plotly_dark", height=280,
            margin=dict(l=0, r=0, t=5, b=30),
            paper_bgcolor=CARD, plot_bgcolor=CARD,
            xaxis_title="Hora apertura (UTC)", yaxis_title="Avg PnL (pips)",
            font=dict(family="Consolas, monospace", size=10),
        )
        st.plotly_chart(fig_heat, use_container_width=True)

    # ── Comparativa de estrategias ──────────────────────────────────────────
    st.markdown('<div class="section-title">🏆 Comparativa de Estrategias</div>', unsafe_allow_html=True)

    comp_rows = []
    df_comp = df_all[~df_all["strategy"].isin(EXCLUDED_STRATEGIES)]
    for (strat, sym), grp in df_comp.groupby(["strategy", "symbol"]):
        k = compute_kpis(grp, initial_capital)
        if not k: continue
        rr = k["avg_win_pips"] / k["avg_loss_pips"] if k["avg_loss_pips"] > 0 else 0
        comp_rows.append({
            "Estrategia": strat, "Par": sym, "Trades": k["total_trades"],
            "Win Rate": f"{k['win_rate']:.1%}",
            "PF": f"{k['profit_factor']:.2f}" if k['profit_factor'] != float('inf') else "inf",
            "Sharpe": f"{k['sharpe']:.2f}", "R:R": f"1:{rr:.2f}",
            "MaxDD%": f"{k['max_dd_pct']:.1f}%",
            "PnL USD": f"${k['total_pnl_usd']:+,.0f}",
            "PnL %": f"{k['total_pnl_pct']:+.2f}%",
        })

    if comp_rows:
        dfc = pd.DataFrame(comp_rows)

        def _col_colors(vals, col):
            colors = []
            for v in vals:
                if col in ("PnL USD","PnL %"):
                    c = GREEN if str(v).startswith("+") else (RED if str(v).startswith("-") else "#FFFFFF")
                elif col == "PF":
                    try:
                        n = float(str(v).replace("inf","999"))
                        c = GREEN if n >= 1.5 else (YELLOW if n >= 1.0 else RED)
                    except: c = "#FFFFFF"
                elif col == "Win Rate":
                    try:
                        n = float(str(v).replace("%",""))
                        c = GREEN if n >= 45 else (YELLOW if n >= 35 else RED)
                    except: c = "#FFFFFF"
                else:
                    c = "#FFFFFF"
                colors.append(c)
            return colors

        fig_comp = go.Figure(go.Table(
            header=dict(
                values=[f"<b>{h}</b>" for h in dfc.columns],
                fill_color="#12152B",
                font=dict(color="#FFFFFF", size=12, family="Consolas, monospace"),
                align="center", height=32, line_color="#2A2D3E",
            ),
            cells=dict(
                values=[dfc[c].tolist() for c in dfc.columns],
                fill_color="#1A1D2E",
                font=dict(
                    color=[_col_colors(dfc[c].tolist(), c) for c in dfc.columns],
                    size=12, family="Consolas, monospace",
                ),
                align="center", height=28, line_color="#2A2D3E",
            ),
        ))
        fig_comp.update_layout(
            template="plotly_dark",
            margin=dict(l=0, r=0, t=0, b=0),
            height=60 + 30 * len(dfc),
            paper_bgcolor="#0E1117",
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    # ── Últimos 20 trades ───────────────────────────────────────────────────
    st.markdown('<div class="section-title">📋 Últimos 20 Trades</div>', unsafe_allow_html=True)

    cols_show = ["strategy","symbol","direction","open_time","outcome",
                 "pnl_pips","pnl_usd","duration_h","notes"]
    dr = df.sort_values("open_time", ascending=False).head(20)[cols_show].copy()
    dr["open_time"]  = dr["open_time"].dt.strftime("%Y-%m-%d %H:%M")
    dr["pnl_pips"]   = dr["pnl_pips"].round(1)
    dr["pnl_usd"]    = dr["pnl_usd"].round(2)
    dr["duration_h"] = dr["duration_h"].round(2)

    col_labels = ["Estrategia","Par","Dir","Apertura","Outcome","PnL Pips","PnL USD","Horas","Notas"]
    row_bg     = ["#1D3028" if p > 0 else "#2E1A1A" if p < 0 else "#1A1D2E" for p in dr["pnl_pips"]]
    pip_colors = ["#00C896" if p > 0 else "#FF4B4B" for p in dr["pnl_pips"]]
    usd_colors = ["#00C896" if p > 0 else "#FF4B4B" for p in dr["pnl_usd"]]

    fig_trades = go.Figure(go.Table(
        columnwidth=[180, 70, 55, 130, 70, 80, 90, 60, 300],
        header=dict(
            values=[f"<b>{h}</b>" for h in col_labels],
            fill_color="#12152B",
            font=dict(color="#FFFFFF", size=11, family="Consolas, monospace"),
            align=["left","center","center","center","center","right","right","right","left"],
            height=30, line_color="#2A2D3E",
        ),
        cells=dict(
            values=[dr[c].tolist() for c in dr.columns],
            fill_color=[row_bg]*9,
            font=dict(
                color=[
                    ["#FFFFFF"]*len(dr), ["#4B9FFF"]*len(dr), ["#FFFFFF"]*len(dr),
                    ["#CCCCCC"]*len(dr), ["#FFD166"]*len(dr),
                    pip_colors, usd_colors,
                    ["#FFFFFF"]*len(dr), ["#AAAAAA"]*len(dr),
                ],
                size=11, family="Consolas, monospace",
            ),
            align=["left","center","center","center","center","right","right","right","left"],
            height=26, line_color="#2A2D3E",
        ),
    ))
    fig_trades.update_layout(
        template="plotly_dark",
        margin=dict(l=0, r=0, t=0, b=0),
        height=80 + 27 * len(dr),
        paper_bgcolor="#0E1117",
    )
    st.plotly_chart(fig_trades, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — CALCULADORA DE MÁRGENES
# ═════════════════════════════════════════════════════════════════════════════
with tab_margin:

    st.markdown('<div class="section-title">📐 Calculadora de Márgenes — IC Markets 1:500</div>',
                unsafe_allow_html=True)
    st.caption("Cuántos trades pueden correr en simultáneo según el capital, con 1% riesgo por trade.")

    LEVERAGE      = 500
    RISK_PCT      = 0.01
    MARGIN_SAFETY = 0.40
    MAX_DD_STOP   = 0.03
    CAPITAL_TIERS = [100, 300, 500, 1_000, 2_500, 5_000, 10_000, 25_000]

    def compute_tier(capital):
        risk_usd        = capital * RISK_PCT
        daily_stop_usd  = capital * MAX_DD_STOP
        margin_budget   = capital * MARGIN_SAFETY
        ref_sl = 15; ref_pip = 10.0
        lot = max(0.01, round(risk_usd / (ref_sl * ref_pip) / 0.01) * 0.01)
        margin_trade = (lot * 100_000 * 1.10) / LEVERAGE
        max_by_margin = int(margin_budget / margin_trade) if margin_trade > 0 else 0
        max_trades    = min(max_by_margin, int(0.06 / RISK_PCT), 6)
        return {
            "capital": capital, "risk_usd": risk_usd, "lot": lot,
            "margin_trade": margin_trade, "max_trades": max(1, max_trades),
            "daily_stop": daily_stop_usd,
            "mode": "Micro" if capital < 500 else ("Mini" if capital < 5000 else "Standard"),
        }

    tiers = [compute_tier(c) for c in CAPITAL_TIERS]

    tier_headers = ["Capital","Riesgo/Trade","Lot Size","Margen/Trade",
                    "Max Trades Simult.","Stop Diario","Modo"]
    tier_vals = [
        [f"${t['capital']:,.0f}"       for t in tiers],
        [f"${t['risk_usd']:.2f}"       for t in tiers],
        [f"{t['lot']:.2f}"             for t in tiers],
        [f"${t['margin_trade']:.2f}"   for t in tiers],
        [str(t['max_trades'])          for t in tiers],
        [f"${t['daily_stop']:.2f}"     for t in tiers],
        [t['mode']                     for t in tiers],
    ]

    highlight   = [GREEN if t["capital"] == initial_capital else "#1A1D2E" for t in tiers]
    txt_cap     = ["#FFFF00" if t["capital"] == initial_capital else "#FFFFFF" for t in tiers]
    trade_clrs  = [GREEN if t["max_trades"] >= 3 else (YELLOW if t["max_trades"] == 2 else RED) for t in tiers]

    fig_margin = go.Figure(go.Table(
        columnwidth=[110,110,90,120,150,110,90],
        header=dict(
            values=[f"<b>{h}</b>" for h in tier_headers],
            fill_color="#12152B",
            font=dict(color="#FFFFFF", size=12, family="Consolas, monospace"),
            align="center", height=34, line_color="#2A2D3E",
        ),
        cells=dict(
            values=tier_vals,
            fill_color=[highlight]*7,
            font=dict(
                color=[txt_cap, ["#FFFFFF"]*8, ["#4B9FFF"]*8, ["#FFFFFF"]*8,
                       trade_clrs, [RED]*8, ["#FFD166"]*8],
                size=13, family="Consolas, monospace",
            ),
            align="center", height=30, line_color="#2A2D3E",
        ),
    ))
    fig_margin.update_layout(
        template="plotly_dark",
        margin=dict(l=0, r=0, t=0, b=0),
        height=60 + 32*len(tiers),
        paper_bgcolor="#0E1117",
    )
    st.plotly_chart(fig_margin, use_container_width=True)

    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        st.markdown("""
        **Regla de escalado:**
        - Nunca superar el 40% del capital en margen
        - Riesgo total acumulado máximo: 6%
        - Stop diario automático si pérdida > 3%
        """)
    with col_r2:
        st.markdown("""
        **Con $300 — modo micro:**
        - 1–2 trades simultáneos
        - Lot 0.02 en pares USD
        - SL máximo recomendado: 15 pips
        - Riesgo real por trade: $3
        """)
    with col_r3:
        st.markdown("""
        **Cuándo subir un nivel:**
        - Capital creció 50% → subir lot
        - Nunca subir lot en drawdown
        - Target antes de retirar: ×3 capital inicial
        """)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
fc1, fc2, fc3 = st.columns(3)
fc1.caption(f"**Datos:** {TRADES_CSV.name if TRADES_CSV.exists() else 'sin datos'}")
fc2.caption("**Modo:** Demo | IC Markets MT5 | Cuenta 52843273")
fc3.caption("**MQ26 BOT v2** — Top 5: BTCUSD · GBPJPY · NZDJPY · EURJPY · AUDUSD | S03 Asian Range")
