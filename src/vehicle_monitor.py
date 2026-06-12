#!/usr/bin/env python
"""
vehicle_monitor.py
OBD-Cortex standalone vehicle data collection daemon.

Continuously polls all supported OBD-II Mode 01 live PIDs from the vehicle's
ECU and logs them as structured JSON records to a rotating file.
Also emits human-readable columnar output to stdout (captured by journald).

This script has NO dependency on cloud provisioning, the telemetry buffer,
or Edge.service. It runs as CanMonitor.service and owns the CAN bus interface.
"""

import sys
import time
import json
import signal
import logging
import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import BASE_DIR
from core.can_interface import init_can_bus, shutdown_can_bus
from services.obd_scanner import (
    ping_ecu,
    read_vin,
    read_supported_pids,
    read_live_pids,
    PID_DECODERS,
)

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
import os

MONITOR_INTERVAL = float(os.getenv("MONITOR_INTERVAL", "1.0"))   # seconds between polls
LOG_DIR          = BASE_DIR / "logs"
LOG_PATH         = LOG_DIR / "vehicle_data.log"
LOG_MAX_BYTES    = 10 * 1024 * 1024   # 10 MB per file
LOG_BACKUP_COUNT = 5                   # keep 5 rotations

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
# Root logger: INFO to stdout (journald)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Separate rotating file logger for structured JSON records
LOG_DIR.mkdir(parents=True, exist_ok=True)
_json_handler = RotatingFileHandler(
    str(LOG_PATH),
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding="utf-8",
)
_json_handler.setFormatter(logging.Formatter("%(message)s"))
_json_logger = logging.getLogger("vehicle_data")
_json_logger.addHandler(_json_handler)
_json_logger.setLevel(logging.INFO)
_json_logger.propagate = False  # do not echo JSON records to stdout


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
_COLUMN_WIDTH = 30
_VALUE_WIDTH  = 12

def _print_header(supported_pids: set):
    """Prints the columnar header line for the live display."""
    names = [PID_DECODERS[p][0] for p in sorted(supported_pids) if p in PID_DECODERS]
    header = "  ".join(f"{n:<{_COLUMN_WIDTH}}" for n in names)
    print(f"\n{'TIMESTAMP':<24}  {header}")
    print("-" * (26 + ((_COLUMN_WIDTH + 2) * len(names))))


def _print_row(timestamp: str, live_pids: dict):
    """Prints a single columnar data row to stdout."""
    row_parts = []
    for pid in sorted(PID_DECODERS.keys()):
        name = PID_DECODERS[pid][0]
        if name in live_pids:
            entry = live_pids[name]
            cell = f"{entry['value']}{entry['unit']}"
        else:
            cell = "--"
        row_parts.append(f"{cell:<{_COLUMN_WIDTH}}")
    print(f"{timestamp:<24}  {'  '.join(row_parts)}")


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_running = True

def _handle_signal(signum, frame):
    """SIGTERM / SIGINT handler -- sets the shutdown flag."""
    global _running
    logger.info(f"Signal {signum} received. Shutting down.")
    _running = False

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT,  _handle_signal)


# ---------------------------------------------------------------------------
# Main daemon loop
# ---------------------------------------------------------------------------
def main():
    global _running

    logger.info("=== OBD-CORTEX VEHICLE MONITOR ===")
    logger.info(f"Poll interval : {MONITOR_INTERVAL}s")
    logger.info(f"JSON log path : {LOG_PATH}")

    # -----------------------------------------------------------------------
    # CAN bus initialisation
    # -----------------------------------------------------------------------
    bus = None
    try:
        bus = init_can_bus()
    except RuntimeError as e:
        logger.error(f"CAN bus error: {e}")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # ECU presence check
    # -----------------------------------------------------------------------
    ecu_found = False
    for attempt in range(1, 6):
        if ping_ecu(bus):
            ecu_found = True
            break
        if attempt < 5:
            logger.warning(f"ECU unresponsive. Retry ({attempt}/5)...")
            time.sleep(2.0)

    if not ecu_found:
        logger.error("ECU did not respond. Is the ignition on?")
        shutdown_can_bus(bus)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # VIN identification (best-effort; monitor continues without it)
    # -----------------------------------------------------------------------
    vin = "UNKNOWN"
    try:
        vin = read_vin(bus)
        logger.info(f"VIN: {vin}")
    except RuntimeError as e:
        logger.warning(f"VIN not available: {e}. Continuing without VIN.")

    # -----------------------------------------------------------------------
    # PID capability probe (once per session)
    # -----------------------------------------------------------------------
    logger.info("Probing ECU for supported PIDs...")
    supported_pids = read_supported_pids(bus)

    if not supported_pids:
        logger.warning("No supported PIDs detected from ECU. "
                       "Vehicle may not support Mode 01 live data.")

    logger.info(f"ECU supports {len(supported_pids)} monitored PIDs. Starting poll loop.")
    _print_header(supported_pids)

    # -----------------------------------------------------------------------
    # Poll loop
    # -----------------------------------------------------------------------
    consecutive_empty = 0
    MAX_EMPTY_BEFORE_RECONNECT = 10

    while _running:
        loop_start = time.time()

        live_pids = read_live_pids(bus, supported_pids)
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if live_pids:
            consecutive_empty = 0

            # Write structured JSON record to rotating log
            record = {"timestamp": ts, "vin": vin, "pids": live_pids}
            _json_logger.info(json.dumps(record))

            # Emit human-readable row to stdout / journald
            _print_row(ts[:23], live_pids)

        else:
            consecutive_empty += 1
            logger.debug(f"Empty PID read ({consecutive_empty}/{MAX_EMPTY_BEFORE_RECONNECT})")

            if consecutive_empty >= MAX_EMPTY_BEFORE_RECONNECT:
                logger.warning("Repeated empty PID reads -- checking ECU and reconnecting CAN bus...")
                consecutive_empty = 0

                if not ping_ecu(bus):
                    logger.warning("ECU unreachable. Attempting CAN bus reconnection...")
                    shutdown_can_bus(bus)
                    time.sleep(2.0)
                    try:
                        bus = init_can_bus()
                        supported_pids = read_supported_pids(bus)
                        _print_header(supported_pids)
                    except RuntimeError as e:
                        logger.error(f"Reconnection failed: {e}. Retrying in 10s...")
                        time.sleep(10.0)

        # Maintain stable poll interval regardless of bus latency
        elapsed = time.time() - loop_start
        sleep_time = max(0.0, MONITOR_INTERVAL - elapsed)
        time.sleep(sleep_time)

    # -----------------------------------------------------------------------
    # Graceful shutdown
    # -----------------------------------------------------------------------
    logger.info("=== OBD-CORTEX VEHICLE MONITOR STOPPED ===")
    shutdown_can_bus(bus)


if __name__ == "__main__":
    main()
