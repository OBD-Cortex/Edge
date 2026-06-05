#!/usr/bin/env python
"""
Embedded-Automotive-Edge Gateway Logger
OBD-Cortex IoT Telemetry Streamer for Raspberry Pi 4.

Orchestrates CAN bus reading, DTC diagnostics, local buffering, and cloud syncing.
Enforces strict physical vehicle connectivity checks and retries during boot.
"""

import os
import sys
import time
import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import (
    RAG_API_URL,
    DEVICE_TOKEN,
    SCAN_INTERVAL,
    HEARTBEAT_INTERVAL,
    RECONNECT_COOLDOWN
)
from core.can_interface import init_can_bus, shutdown_can_bus
from services.obd_scanner import ping_ecu, read_vin, run_full_scan
from services.dtc_sanitizer import enrich_dtc, build_scan_summary, has_state_changed
from core.telemetry_buffer import init_buffer, save_to_buffer, flush_to_cloud
from services.cloud_sync import decode_vin
from core.crypto import is_provisioned
from services.provisioning import provision_device

def build_telemetry_document(vin, raw_scan):
    """
    Assembles raw scan results into a fully enriched telemetry snapshot document.
    """
    confirmed_enriched = [enrich_dtc(c) for c in raw_scan["confirmed_dtcs"]]
    pending_enriched = [enrich_dtc(p) for p in raw_scan["pending_dtcs"]]
    
    # System Status rules:
    # - "critical" if any active DTC has severity == "critical"
    # - "warning" if any DTCs exist but none are critical
    # - "healthy" if no DTCs exist and MIL is inactive
    severities = [d["severity"] for d in confirmed_enriched + pending_enriched]
    if "critical" in severities:
        system_status = "critical"
    elif severities:
        system_status = "warning"
    else:
        system_status = "healthy"

    scan_summary = build_scan_summary(
        raw_scan["mil_active"],
        confirmed_enriched,
        pending_enriched
    )

    return {
        "vehicle_id": vin,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mil_active": raw_scan["mil_active"],
        "dtc_count": len(confirmed_enriched) + len(pending_enriched),
        "confirmed_dtcs": confirmed_enriched,
        "pending_dtcs": pending_enriched,
        "system_status": system_status,
        "scan_summary": scan_summary
    }

def main():
    logger.info("--- OBD-CORTEX DATA LOGGER ---")

    redacted_token = f"{DEVICE_TOKEN[:8]}..." if DEVICE_TOKEN else "None"
    logger.info(f"Device Token: {redacted_token}")
    logger.info(f"Scan Interval: {SCAN_INTERVAL}s")
    logger.info(f"Heartbeat Interval: {HEARTBEAT_INTERVAL}s")
    logger.info("Press Ctrl+C to exit.")

    # 1. Initialize hardware interfaces and local buffer
    bus = None
    try:
        bus = init_can_bus()
    except RuntimeError as e:
        logger.error(f"Hardware error: {e}")
        sys.exit(1)

    init_buffer()

    # 2. ECU Verification / Ping Phase
    # Retries Service 01 PID 00 up to 5 times (total 10 seconds timeout) to handle boot delay
    ecu_found = False
    ping_attempts = 5
    for attempt in range(1, ping_attempts + 1):
        if ping_ecu(bus):
            ecu_found = True
            break
        if attempt < ping_attempts:
            logger.warning(f"Vehicle ECU is unresponsive. Waiting 2s before retry {attempt + 1}/{ping_attempts}...")
            time.sleep(2.0)

    if not ecu_found:
        logger.error("Vehicle ECU did not respond. Is the ignition on?")
        shutdown_can_bus(bus)
        sys.exit(1)

    # 3. Read Vehicle Identification Number (VIN)
    # Internally retries up to 3 times
    try:
        vin = read_vin(bus)
        logger.info(f"VEHICLE VIN IDENTIFIED: {vin}")
    except RuntimeError as e:
        logger.error(str(e))
        shutdown_can_bus(bus)
        sys.exit(1)

    # 4. Check API Configuration
    if not RAG_API_URL:
        logger.error("Required environment variable RAG_API_URL is missing.")
        shutdown_can_bus(bus)
        sys.exit(1)

    logger.info(f"Connected to Central API Server: {RAG_API_URL}")

    # 5. NHTSA Decode vehicle info
    brand, model, year = decode_vin(vin)

    # 6. Provisioning Gate
    if not is_provisioned():
        logger.info("Device is not provisioned. Initiating provisioning flow...")
        if not DEVICE_TOKEN:
            logger.error("DEVICE_TOKEN is missing. Cannot provision device without a registration token.")
            shutdown_can_bus(bus)
            sys.exit(1)
        try:
            device_id = provision_device(vin, brand, model, year)
        except Exception as e:
            logger.error(f"Provisioning failed: {e}")
            shutdown_can_bus(bus)
            sys.exit(1)
    else:
        from core.config import DEVICE_ID
        logger.info(f"Device is already provisioned (Device ID: {DEVICE_ID}). Skipping provisioning.")

    # 6. Core Streaming loop
    last_scan_state = None
    last_heartbeat_time = 0.0
    last_reconnect_time = 0.0

    try:
        while True:
            current_time = time.time()
            
            # Reconnection/Keep-alive logic placeholder
            if current_time - last_reconnect_time > RECONNECT_COOLDOWN:
                last_reconnect_time = current_time

            # A. Run full diagnostic scan
            raw_scan = run_full_scan(bus)

            # B. Evaluate trigger conditions
            heartbeat_due = (current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL)
            state_changed = has_state_changed(raw_scan, last_scan_state)

            if state_changed or heartbeat_due:
                reason = "DTC State Changed" if state_changed else "Heartbeat Interval Elapsed"
                logger.info(f"Triggering telemetry capture. Reason: {reason}")
                
                # Assemble telemetry snapshot document
                telemetry = build_telemetry_document(vin, raw_scan)

                # Store snapshot in local SQLite buffer first (ensures zero data loss)
                save_to_buffer(telemetry)

                # Attempt to flush the SQLite buffer to the Cloud API
                flush_to_cloud()
                    
                # Reset timers and state tracking
                last_scan_state = raw_scan
                last_heartbeat_time = current_time
            else:
                # Telemetry skipped because state is unchanged and heartbeat is not due
                pass

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
