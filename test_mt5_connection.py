"""
Test de conexión MT5 — IC Markets Demo
Ejecutar: python test_mt5_connection.py
"""
import sys, os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
sys.path.insert(0, str(Path(__file__).parent))

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")

from execution.mt5_connector import MT5Connector

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "EURJPY", "NZDUSD", "XAUUSD"]

def diagnose_terminal():
    """Verifica el estado del terminal MT5 antes de conectar."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("  [ERROR] MetaTrader5 no instalado: pip install MetaTrader5")
        return

    # Verificar si el terminal ya esta inicializado
    term = mt5.terminal_info()
    if term is not None:
        print(f"  Terminal ya activo: build={term.build}, path={term.path}")
        print(f"  Connected={term.connected}, trade_allowed={term.trade_allowed}")
    else:
        print("  Terminal no inicializado aun (se intentara en connect())")

    # Verificar paths conocidos
    from pathlib import Path
    paths = [
        r"C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe",
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
    ]
    for p in paths:
        exists = Path(p).exists()
        print(f"  {'[OK]' if exists else '[--]'} {p}")


def main():
    print("=" * 60)
    print("  MQ26 BOT v2 — Test de Conexion MT5")
    print("=" * 60)

    print("\n--- DIAGNOSTICO PREVIO ---")
    diagnose_terminal()

    conn = MT5Connector()

    # 1. Conectar
    if not conn.connect():
        print("\nFALLO: No se pudo conectar a MT5.")
        print("Verificar: MT5 abierto, login/password/server en .env")
        sys.exit(1)

    # 2. Info de cuenta
    print("\n--- CUENTA ---")
    acc = conn.get_account_info()
    if acc:
        print(f"  Login:      {acc['login']}")
        print(f"  Servidor:   {acc['server']}")
        print(f"  Empresa:    {acc['company']}")
        print(f"  Balance:    ${acc['balance']:,.2f} {acc['currency']}")
        print(f"  Equity:     ${acc['equity']:,.2f} {acc['currency']}")
        print(f"  Margen lib: ${acc['free_margin']:,.2f}")
        print(f"  Leverage:   1:{acc['leverage']}")

    # 3. Precios en tiempo real
    print("\n--- PRECIOS EN TIEMPO REAL ---")
    print(f"  {'Par':<10} {'Bid':>10} {'Ask':>10} {'Spread':>8}")
    print(f"  {'-'*40}")
    for sym in PAIRS:
        tick = conn.get_tick(sym)
        if tick:
            print(f"  {sym:<10} {tick['bid']:>10.5f} {tick['ask']:>10.5f} {tick['spread']:>6.1f} pips")
        else:
            print(f"  {sym:<10} --- no disponible ---")

    # 4. OHLCV últimas 5 velas M5
    print("\n--- OHLCV EURUSD M5 (ultimas 5 velas) ---")
    df = conn.get_ohlcv("EURUSD", timeframe="M5", n_bars=5)
    if not df.empty:
        print(df.to_string())
    else:
        print("  Sin datos OHLCV")

    # 5. Posiciones abiertas
    print("\n--- POSICIONES ABIERTAS ---")
    positions = conn.get_open_positions()
    if positions:
        for p in positions:
            print(f"  {p['direction']} {p['volume']} {p['symbol']} @ {p['open_price']} | PnL: ${p['profit']:.2f}")
    else:
        print("  Sin posiciones abiertas")

    conn.disconnect()
    print("\nConexion MT5: OK")
    print("=" * 55)

if __name__ == "__main__":
    main()
