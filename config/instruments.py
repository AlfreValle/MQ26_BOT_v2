"""
Definición de instrumentos por clase de activo.
Incluye: pares forex, índices, oro — con sus especificaciones.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Instrument:
    symbol: str                  # Símbolo en MT5
    yf_symbol: str               # Símbolo en Yahoo Finance
    asset_class: str             # "forex" | "index" | "gold"
    pip_size: float              # Valor de 1 pip (e.g. 0.0001 para EURUSD)
    spread_typical: float        # Spread típico en pips (IC Markets ECN)
    pip_value_usd: float = 0.0  # USD por pip por lote estándar (0 = calcular)
    min_lot: float = 0.01
    lot_step: float = 0.01
    contract_size: float = 100_000.0   # Unidades por lote estándar
    margin_pct: float = 0.002          # Margen requerido (0.2% = 1:500 leverage)
    description: str = ""
    active: bool = True
    max_spread_pips: float = 0.0       # Filtro: no operar si spread > X pips
    # #62 — Commission-aware sizing: comisión round-turn en USD por lote estándar
    # IC Markets Raw Spread: ~$3.50/lot RT para Forex; ~$0.02/lot RT para BTCUSD
    commission_rt: float = 3.50        # USD round-turn por lote (entrada + salida)

    def __post_init__(self):
        if self.max_spread_pips == 0.0:
            self.max_spread_pips = self.spread_typical * 3.0
        # Si no se especificó pip_value_usd, usar pip_size * contract_size
        # (correcto para pares con USD como cotización)
        if self.pip_value_usd == 0.0:
            self.pip_value_usd = self.pip_size * self.contract_size

    def margin_per_lot(self, price: float) -> float:
        """Margen requerido en USD para 1 lote estándar."""
        return self.contract_size * price * self.margin_pct

    def margin_micro_lot(self, price: float) -> float:
        """Margen requerido en USD para 0.01 lote (micro lot)."""
        return self.margin_per_lot(price) * 0.01


# ─── FOREX — universo completo IC Markets ─────────────────────────────────────
FOREX_INSTRUMENTS: dict[str, Instrument] = {
    # ── Majors USD como cotización → $10/pip/lote
    "EURUSD": Instrument(
        symbol="EURUSD", yf_symbol="EURUSD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=10.0, spread_typical=0.1,
        description="Euro / US Dollar",
    ),
    "GBPUSD": Instrument(
        symbol="GBPUSD", yf_symbol="GBPUSD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=10.0, spread_typical=0.3,
        description="British Pound / US Dollar",
    ),
    "AUDUSD": Instrument(
        symbol="AUDUSD", yf_symbol="AUDUSD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=10.0, spread_typical=0.2,
        description="Australian Dollar / US Dollar",
    ),
    "NZDUSD": Instrument(
        symbol="NZDUSD", yf_symbol="NZDUSD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=10.0, spread_typical=0.4,
        description="New Zealand Dollar / US Dollar",
    ),
    "CADUSD": Instrument(
        symbol="CADUSD", yf_symbol="CADUSD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=10.0, spread_typical=0.3,
        description="Canadian Dollar / US Dollar",
    ),
    # ── Majors USD como base
    "USDJPY": Instrument(
        symbol="USDJPY", yf_symbol="USDJPY=X", asset_class="forex",
        pip_size=0.01, pip_value_usd=6.50, spread_typical=0.3,
        description="US Dollar / Japanese Yen",
    ),
    "USDCAD": Instrument(
        symbol="USDCAD", yf_symbol="USDCAD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=7.25, spread_typical=0.3,
        description="US Dollar / Canadian Dollar",
    ),
    "USDCHF": Instrument(
        symbol="USDCHF", yf_symbol="USDCHF=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=11.20, spread_typical=0.4,
        description="US Dollar / Swiss Franc",
    ),
    "USDMXN": Instrument(
        symbol="USDMXN", yf_symbol="USDMXN=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=0.58, spread_typical=2.5, max_spread_pips=8.0,
        description="US Dollar / Mexican Peso",
    ),
    "USDBRL": Instrument(
        symbol="USDBRL", yf_symbol="USDBRL=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=1.95, spread_typical=3.0, max_spread_pips=10.0,
        description="US Dollar / Brazilian Real",
    ),
    # ── JPY crosses → pip_value ≈ $6.50/pip/lote
    "EURJPY": Instrument(
        symbol="EURJPY", yf_symbol="EURJPY=X", asset_class="forex",
        pip_size=0.01, pip_value_usd=6.50, spread_typical=0.5,
        description="Euro / Japanese Yen",
    ),
    "GBPJPY": Instrument(
        symbol="GBPJPY", yf_symbol="GBPJPY=X", asset_class="forex",
        pip_size=0.01, pip_value_usd=6.50, spread_typical=0.8,
        description="British Pound / Japanese Yen",
    ),
    "AUDJPY": Instrument(
        symbol="AUDJPY", yf_symbol="AUDJPY=X", asset_class="forex",
        pip_size=0.01, pip_value_usd=6.50, spread_typical=0.6,
        description="Australian Dollar / Japanese Yen",
    ),
    "NZDJPY": Instrument(
        symbol="NZDJPY", yf_symbol="NZDJPY=X", asset_class="forex",
        pip_size=0.01, pip_value_usd=6.50, spread_typical=0.8,
        description="New Zealand Dollar / Japanese Yen",
    ),
    "CADJPY": Instrument(
        symbol="CADJPY", yf_symbol="CADJPY=X", asset_class="forex",
        pip_size=0.01, pip_value_usd=6.50, spread_typical=0.7,
        description="Canadian Dollar / Japanese Yen",
    ),
    "CHFJPY": Instrument(
        symbol="CHFJPY", yf_symbol="CHFJPY=X", asset_class="forex",
        pip_size=0.01, pip_value_usd=6.50, spread_typical=0.7,
        description="Swiss Franc / Japanese Yen",
    ),
    # ── GBP crosses → pip_value según cotización
    "GBPAUD": Instrument(
        symbol="GBPAUD", yf_symbol="GBPAUD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=6.20, spread_typical=0.8,  # AUD→USD ~0.62
        description="British Pound / Australian Dollar",
    ),
    "GBPCAD": Instrument(
        symbol="GBPCAD", yf_symbol="GBPCAD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=7.25, spread_typical=0.9,
        description="British Pound / Canadian Dollar",
    ),
    "GBPNZD": Instrument(
        symbol="GBPNZD", yf_symbol="GBPNZD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=5.80, spread_typical=1.2,  # NZD→USD ~0.58
        description="British Pound / New Zealand Dollar",
    ),
    "GBPCHF": Instrument(
        symbol="GBPCHF", yf_symbol="GBPCHF=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=11.20, spread_typical=1.0,
        description="British Pound / Swiss Franc",
    ),
    # ── EUR crosses
    "EURGBP": Instrument(
        symbol="EURGBP", yf_symbol="EURGBP=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=12.60, spread_typical=0.4,
        description="Euro / British Pound",
    ),
    "EURCHF": Instrument(
        symbol="EURCHF", yf_symbol="EURCHF=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=11.20, spread_typical=0.6,
        description="Euro / Swiss Franc",
    ),
    "EURAUD": Instrument(
        symbol="EURAUD", yf_symbol="EURAUD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=6.20, spread_typical=0.7,
        description="Euro / Australian Dollar",
    ),
    "EURCAD": Instrument(
        symbol="EURCAD", yf_symbol="EURCAD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=7.25, spread_typical=0.7,
        description="Euro / Canadian Dollar",
    ),
    # ── AUD crosses
    "AUDCAD": Instrument(
        symbol="AUDCAD", yf_symbol="AUDCAD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=7.25, spread_typical=0.6,
        description="Australian Dollar / Canadian Dollar",
    ),
    "AUDNZD": Instrument(
        symbol="AUDNZD", yf_symbol="AUDNZD=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=5.80, spread_typical=0.8,
        description="Australian Dollar / New Zealand Dollar",
    ),
    "AUDCHF": Instrument(
        symbol="AUDCHF", yf_symbol="AUDCHF=X", asset_class="forex",
        pip_size=0.0001, pip_value_usd=11.20, spread_typical=0.7,
        description="Australian Dollar / Swiss Franc",
    ),
    # ── Oro
    "XAUUSD": Instrument(
        symbol="XAUUSD", yf_symbol="GC=F", asset_class="gold",
        pip_size=0.01, pip_value_usd=1.0, spread_typical=5.0,
        # spread_typical=5.0 → (ask-bid)/point/10 ≈ $0.50/0.01/10 = 5 "pips"
        # max_spread_pips=50 → $5 máximo (muy amplio para sesión pre-Asia)
        max_spread_pips=50.0,
        contract_size=100.0, margin_pct=0.005,
        commission_rt=0.0,   # IC Markets: XAUUSD es spread-only (sin comisión fija)
        description="Gold / US Dollar (XAU/USD)",
    ),
}

# ─── ÍNDICES — IC Markets CFDs ────────────────────────────────────────────────
# IC Markets CFD: 1 lote = $1/punto. Min lot = 0.1.
# pip_size = 1 punto (unidad mínima de cotización del índice).
INDEX_INSTRUMENTS: dict[str, Instrument] = {
    "SP500": Instrument(
        symbol="US500",    yf_symbol="^GSPC",  asset_class="index",
        pip_size=1.0, pip_value_usd=1.0, spread_typical=0.4,
        contract_size=1.0, margin_pct=0.005,  # 1:200 leverage en índices
        min_lot=0.1, lot_step=0.1,
        max_spread_pips=3.0,
        description="S&P 500 CFD — IC Markets US500",
    ),
    "NASDAQ": Instrument(
        symbol="NAS100",   yf_symbol="^NDX",   asset_class="index",
        pip_size=1.0, pip_value_usd=1.0, spread_typical=0.6,
        contract_size=1.0, margin_pct=0.005,
        min_lot=0.1, lot_step=0.1,
        max_spread_pips=4.0,
        description="NASDAQ 100 CFD — IC Markets NAS100",
    ),
    "RUSSELL": Instrument(
        symbol="US2000",   yf_symbol="^RUT",   asset_class="index",
        pip_size=0.1, pip_value_usd=1.0, spread_typical=0.4,
        contract_size=1.0, margin_pct=0.005,
        min_lot=0.1, lot_step=0.1,
        max_spread_pips=3.0,
        description="Russell 2000 CFD — IC Markets US2000",
    ),
    "DOW": Instrument(
        symbol="US30",     yf_symbol="^DJI",   asset_class="index",
        pip_size=1.0, pip_value_usd=1.0, spread_typical=1.5,
        contract_size=1.0, margin_pct=0.005,
        min_lot=0.1, lot_step=0.1,
        max_spread_pips=6.0,
        description="Dow Jones 30 CFD — IC Markets US30",
    ),
}

# ─── ORO (ya incluido en FOREX_INSTRUMENTS como XAUUSD) ──────────────────────
GOLD_INSTRUMENTS: dict[str, Instrument] = {
    "XAUUSD": FOREX_INSTRUMENTS["XAUUSD"],
}

# ─── CRYPTO CFDs — IC Markets MT5 ────────────────────────────────────────────
# IC Markets: 1 lote = 1 unidad de cripto. Margen ~2% (1:50 máx en pro).
# pip_size: mínima fluctuación de precio (1 USD para BTC, 0.01 para alts).
# pip_value = pip_size × contract_size = pip_size × 1 = pip_size USD/pip/lot.
# Spread: varía mucho — usar spread_typical conservador.
CRYPTO_INSTRUMENTS: dict[str, Instrument] = {
    "BTCUSD": Instrument(
        symbol="BTCUSD",  yf_symbol="BTC-USD",  asset_class="crypto",
        pip_size=1.0, pip_value_usd=1.0, spread_typical=15.0,
        contract_size=1.0, margin_pct=0.02,
        min_lot=0.01, lot_step=0.01, max_spread_pips=60.0,
        commission_rt=0.0,   # IC Markets: sin comisión fija en crypto (spread-only)
        description="Bitcoin / US Dollar — IC Markets CFD",
    ),
    "ETHUSD": Instrument(
        symbol="ETHUSD",  yf_symbol="ETH-USD",  asset_class="crypto",
        pip_size=0.01, pip_value_usd=0.01, spread_typical=1.5,
        contract_size=1.0, margin_pct=0.02,
        min_lot=0.1, lot_step=0.1, max_spread_pips=6.0,
        commission_rt=0.0,   # IC Markets: sin comisión fija en crypto
        description="Ethereum / US Dollar — IC Markets CFD",
    ),
    "SOLUSD": Instrument(
        symbol="SOLUSD",  yf_symbol="SOL-USD",  asset_class="crypto",
        pip_size=0.001, pip_value_usd=0.001, spread_typical=0.05,
        contract_size=1.0, margin_pct=0.02,
        min_lot=1.0, lot_step=1.0, max_spread_pips=0.2,
        description="Solana / US Dollar — IC Markets CFD",
    ),
    "XRPUSD": Instrument(
        symbol="XRPUSD",  yf_symbol="XRP-USD",  asset_class="crypto",
        pip_size=0.0001, pip_value_usd=0.0001, spread_typical=0.0005,
        contract_size=1.0, margin_pct=0.02,
        min_lot=10.0, lot_step=10.0, max_spread_pips=0.002,
        description="Ripple / US Dollar — IC Markets CFD",
    ),
    "LTCUSD": Instrument(
        symbol="LTCUSD",  yf_symbol="LTC-USD",  asset_class="crypto",
        pip_size=0.01, pip_value_usd=0.01, spread_typical=0.15,
        contract_size=1.0, margin_pct=0.02,
        min_lot=0.1, lot_step=0.1, max_spread_pips=0.6,
        description="Litecoin / US Dollar — IC Markets CFD",
    ),
    "ADAUSD": Instrument(
        symbol="ADAUSD",  yf_symbol="ADA-USD",  asset_class="crypto",
        pip_size=0.0001, pip_value_usd=0.0001, spread_typical=0.0008,
        contract_size=1.0, margin_pct=0.02,
        min_lot=10.0, lot_step=10.0, max_spread_pips=0.003,
        description="Cardano / US Dollar — IC Markets CFD",
    ),
    "DOTUSD": Instrument(
        symbol="DOTUSD",  yf_symbol="DOT-USD",  asset_class="crypto",
        pip_size=0.001, pip_value_usd=0.001, spread_typical=0.02,
        contract_size=1.0, margin_pct=0.02,
        min_lot=1.0, lot_step=1.0, max_spread_pips=0.08,
        description="Polkadot / US Dollar — IC Markets CFD",
    ),
    "DOGEUSD": Instrument(
        symbol="DOGEUSD", yf_symbol="DOGE-USD", asset_class="crypto",
        pip_size=0.00001, pip_value_usd=0.00001, spread_typical=0.0001,
        contract_size=1.0, margin_pct=0.02,
        min_lot=100.0, lot_step=100.0, max_spread_pips=0.0004,
        description="Dogecoin / US Dollar — IC Markets CFD",
    ),
}

# ─── Agrupaciones por estrategia ──────────────────────────────────────────────
# Mejores pares para cada estrategia forex
LONDON_KILLZONE_PAIRS = ["EURUSD", "GBPUSD", "GBPJPY"]
FVG_RETEST_PAIRS = ["EURUSD", "USDJPY", "AUDUSD", "GBPUSD"]
ASIAN_RANGE_PAIRS = ["GBPJPY", "AUDJPY", "NZDUSD", "EURJPY", "USDJPY"]

# Índices prioritarios para ORB (mayor liquidez)
ORB_INDICES = ["SP500", "NASDAQ"]
VWAP_BOUNCE_INDICES = ["SP500", "DOW"]
GAP_INDICES = ["SP500", "NASDAQ"]

# Crypto — mejores candidatos por liquidez y volatilidad
CRYPTO_ASIAN_PAIRS  = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD"]
CRYPTO_LONDON_PAIRS = ["BTCUSD", "ETHUSD", "SOLUSD"]

# Lookup unificado
ALL_INSTRUMENTS: dict[str, Instrument] = {
    **FOREX_INSTRUMENTS,
    **INDEX_INSTRUMENTS,
    **CRYPTO_INSTRUMENTS,
}


def get_instrument(symbol: str) -> Instrument:
    """Retorna el instrumento por símbolo MT5 o yfinance."""
    inst = ALL_INSTRUMENTS.get(symbol.upper())
    if inst:
        return inst
    # Buscar por yf_symbol
    for i in ALL_INSTRUMENTS.values():
        if i.yf_symbol == symbol:
            return i
    raise KeyError(f"Instrumento no encontrado: {symbol!r}")


def pips_to_price(instrument: Instrument, pips: float) -> float:
    """Convierte pips a precio absoluto."""
    return pips * instrument.pip_size


def price_to_pips(instrument: Instrument, price_diff: float) -> float:
    """Convierte diferencia de precio a pips."""
    return price_diff / instrument.pip_size
