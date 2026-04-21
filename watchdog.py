"""
#33 — Watchdog Process

Proceso independiente que monitorea el bot MQ26 y lo reinicia si se cae.

Características:
  - Verifica que demo_trader.py esté corriendo cada 60s
  - Si el proceso muere, lo reinicia automáticamente con los mismos argumentos
  - Envía alerta Telegram en cada reinicio
  - Escribe heartbeat cada 5min al archivo watchdog.json
  - Máximo 3 reinicios por hora (anti-loop infinito en caso de error recurrente)

Uso (en terminal separado):
    python watchdog.py --cmd "python demo_trader.py --capital 2139 --symbol AUDUSD NZDUSD GBPUSD XAUUSD BTCUSD"

Parar:
    Ctrl+C
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | watchdog — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/logs/watchdog.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("watchdog")

CHECK_INTERVAL   = 60      # segundos entre checks
MAX_RESTARTS_1H  = 6       # máximo reinicios en 1 hora (aumentado para deployments)
HEARTBEAT_FILE   = Path("data/logs/watchdog.json")


def send_telegram(msg: str) -> None:
    """Envía alerta Telegram usando el alerter del bot."""
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
        from core.telegram_alerts import build_alerter_from_settings
        alerter = build_alerter_from_settings()
        alerter.send(msg)
    except Exception as e:
        logger.warning(f"Telegram alert failed: {e}")


def write_heartbeat(status: str, pid: int | None) -> None:
    HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "status": status,
        "pid":    pid,
        "ts":     datetime.now(timezone.utc).isoformat(),
    }
    HEARTBEAT_FILE.write_text(json.dumps(data, indent=2))


def run_watchdog(cmd: str) -> None:
    logger.info("=" * 60)
    logger.info("  MQ26 BOT v2 — WATCHDOG ACTIVO")
    logger.info(f"  Comando: {cmd}")
    logger.info(f"  Check cada: {CHECK_INTERVAL}s | Max reinicios/hora: {MAX_RESTARTS_1H}")
    logger.info("=" * 60)

    restart_times: deque[float] = deque()   # timestamps de reinicios en la última hora
    process: subprocess.Popen | None = None

    def start_bot() -> subprocess.Popen:
        logger.info(f"▶ Iniciando bot: {cmd}")
        return subprocess.Popen(
            cmd, shell=True,
            stdout=None, stderr=None,   # heredar stdout/stderr del padre
        )

    try:
        process = start_bot()
        send_telegram("🐕 Watchdog iniciado — monitoreando MQ26 BOT")
        write_heartbeat("running", process.pid)

        while True:
            time.sleep(CHECK_INTERVAL)

            # Limpiar reinicios viejos (> 1 hora)
            now_ts = time.time()
            while restart_times and now_ts - restart_times[0] > 3600:
                restart_times.popleft()

            # Verificar si el proceso sigue vivo
            if process.poll() is not None:
                exit_code = process.returncode
                logger.warning(f"⚠️ Bot terminó con código {exit_code}")

                if len(restart_times) >= MAX_RESTARTS_1H:
                    logger.critical(
                        f"🚨 Máximo de reinicios ({MAX_RESTARTS_1H}/hora) alcanzado. "
                        f"Watchdog detenido — revisar manualmente."
                    )
                    send_telegram(
                        f"🚨 <b>WATCHDOG DETENIDO</b>\n"
                        f"{MAX_RESTARTS_1H} reinicios en 1 hora.\n"
                        f"Revisar bot manualmente."
                    )
                    write_heartbeat("stopped_max_restarts", None)
                    break

                logger.info("🔄 Reiniciando bot...")
                send_telegram(
                    f"🔄 <b>BOT REINICIADO</b> (watchdog)\n"
                    f"Exit code: {exit_code}\n"
                    f"Reinicios esta hora: {len(restart_times)+1}/{MAX_RESTARTS_1H}"
                )
                restart_times.append(now_ts)
                process = start_bot()
                write_heartbeat("restarted", process.pid)
            else:
                write_heartbeat("running", process.pid)
                logger.debug(f"✅ Bot corriendo (PID={process.pid})")

    except KeyboardInterrupt:
        logger.info("Watchdog detenido por usuario.")
        if process and process.poll() is None:
            process.terminate()
            logger.info("Bot terminado.")
        send_telegram("⏹️ Watchdog detenido manualmente.")
        write_heartbeat("stopped_manual", None)


def main() -> None:
    parser = argparse.ArgumentParser(description="MQ26 BOT v2 — Watchdog")
    parser.add_argument(
        "--cmd", "-c",
        default=".venv\\Scripts\\python.exe demo_trader.py --capital 2139 --symbol BTCUSD XAUUSD AUDUSD NZDUSD ETHUSD GBPUSD EURUSD AUDJPY",
        help="Comando a monitorear",
    )
    args = parser.parse_args()
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    run_watchdog(args.cmd)


if __name__ == "__main__":
    main()
