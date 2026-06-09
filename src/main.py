#!/usr/bin/env python
"""
Embedded-Automotive-Edge Gateway Logger
OBD-Cortex IoT Telemetry Streamer for Raspberry Pi 4.

Orchestrates CAN bus reading, DTC diagnostics, local buffering, and cloud syncing.
Enforces strict physical vehicle connectivity checks and retries during boot.
"""

import sys
import time
import datetime
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import RAG_API_URL, DEVICE_TOKEN, SCAN_INTERVAL, HEARTBEAT_INTERVAL
from core.can_interface import init_can_bus, shutdown_can_bus
from services.obd_scanner import ping_ecu, read_vin, run_full_scan
from services.dtc_sanitizer import enrich_dtc, build_scan_summary, has_state_changed
from core.telemetry_buffer import init_buffer, save_to_buffer, flush_to_cloud
from services.cloud_sync import decode_vin
from core.crypto import is_provisioned
from services.provisioning import provision_device

def build_telemetry_document(vin, raw_scan):
    """Assembles raw scan results into a fully enriched telemetry snapshot document."""
    confirmed = [enrich_dtc(c) for c in raw_scan.get("confirmed_dtcs", [])]
    pending = [enrich_dtc(p) for p in raw_scan.get("pending_dtcs", [])]
    
    severities = {d["severity"] for d in confirmed + pending}
    system_status = "critical" if "critical" in severities else "warning" if severities else "healthy"

    return {
        "vehicle_id": vin,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mil_active": raw_scan.get("mil_active", False),
        "dtc_count": len(confirmed) + len(pending),
        "confirmed_dtcs": confirmed,
        "pending_dtcs": pending,
        "system_status": system_status,
        "scan_summary": build_scan_summary(raw_scan.get("mil_active", False), confirmed, pending)
    }

def main():
    logger.info("--- OBD-CORTEX DATA LOGGER ---")
    logger.info(f"Scan Interval: {SCAN_INTERVAL}s | Heartbeat: {HEARTBEAT_INTERVAL}s")

    bus = None
    try:
        bus = init_can_bus()
    except RuntimeError as e:
        logger.error(f"Hardware error: {e}")
        sys.exit(1)

    init_buffer()

    ecu_found = False
    for attempt in range(1, 6):
        if ping_ecu(bus):
            ecu_found = True
            break
        if attempt < 5:
            logger.warning(f"Vehicle ECU unresponsive. Retrying ({attempt}/5)...")
            time.sleep(2.0)

    if not ecu_found:
        logger.error("Vehicle ECU did not respond. Is the ignition on?")
        shutdown_can_bus(bus)
        sys.exit(1)

    try:
        vin = read_vin(bus)
        logger.info(f"VEHICLE VIN IDENTIFIED: {vin}")
    except RuntimeError as e:
        logger.error(str(e))
        shutdown_can_bus(bus)
        sys.exit(1)

    if not RAG_API_URL:
        logger.error("Required environment variable RAG_API_URL is missing.")
        shutdown_can_bus(bus)
        sys.exit(1)

    logger.info(f"Connected to Central API Server: {RAG_API_URL}")

    brand, model, year = decode_vin(vin)

    if not is_provisioned():
        logger.info("Device not provisioned. Initiating provisioning flow...")
        if not DEVICE_TOKEN:
            logger.error("DEVICE_TOKEN missing. Cannot provision.")
            shutdown_can_bus(bus)
            sys.exit(1)
        try:
            provision_device(vin, brand, model, year)
        except Exception as e:
            logger.error(f"Provisioning failed: {e}")
            shutdown_can_bus(bus)
            sys.exit(1)
    else:
        from core.config import DEVICE_ID
        logger.info(f"Device already provisioned (Device ID: {DEVICE_ID}).")

    last_scan_state = None
    last_heartbeat_time = 0.0

    try:
        while True:
            current_time = time.time()
            raw_scan = run_full_scan(bus)

            heartbeat_due = (current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL)
            state_changed = has_state_changed(raw_scan, last_scan_state)

            if state_changed or heartbeat_due:
                logger.info(f"Triggering telemetry capture. Reason: {'State Changed' if state_changed else 'Heartbeat'}")
                telemetry = build_telemetry_document(vin, raw_scan)
                save_to_buffer(telemetry)
                flush_to_cloud()
                    
                last_scan_state = raw_scan
                last_heartbeat_time = current_time

            time.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Logger process terminated by user.")
    except Exception as e:
        logger.error(f"Critical loop error: {e}")
    finally:
        logger.info("--- SHUTTING DOWN OBD-CORTEX LOGGER ---")
        shutdown_can_bus(bus)

if __name__ == "__main__":
    main()
