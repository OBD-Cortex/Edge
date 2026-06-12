#!/usr/bin/env python
"""
Edge Gateway Logger
OBD-Cortex IoT Telemetry Streamer for Raspberry Pi 4.

Orchestrates CAN bus reading, full OBD-II diagnostics (DTCs + live PIDs +
freeze frame), local buffering, and cloud syncing.
Enforces strict physical vehicle connectivity checks and retries during boot.
Handles automatic re-provisioning when the server returns HTTP 403.
"""

import sys
import time
import datetime
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import EDGE_SERVICE_URL, DEVICE_TOKEN, SCAN_INTERVAL, HEARTBEAT_INTERVAL
from core.can_interface import init_can_bus, shutdown_can_bus
from core.vin_decoder import decode_vin
from services.obd_scanner import ping_ecu, read_vin, run_full_scan, read_supported_pids
from services.dtc_sanitizer import enrich_dtc, build_scan_summary, has_state_changed
from core.telemetry_buffer import init_buffer, save_to_buffer, flush_to_cloud
from core.crypto import is_provisioned
from services.provisioning import provision_device, clear_provisioning_keys


def do_provision(vin: str, vin_info: dict):
    """
    Runs the provisioning handshake using locally decoded VIN metadata.
    Raises RuntimeError on failure so the caller can decide to abort.
    """
    if not DEVICE_TOKEN:
        raise RuntimeError("DEVICE_TOKEN missing in .env. Cannot provision.")

    brand = vin_info.get("brand", "Unknown")
    year  = str(vin_info.get("year", "Unknown"))

    provision_device(vin, brand, "Unknown", year)


def build_telemetry_document(vin: str, vin_info: dict, raw_scan: dict) -> dict:
    """
    Assembles raw scan results into a fully enriched telemetry snapshot document.
    Includes live PIDs and freeze frame data alongside DTC diagnostics.
    """
    confirmed = [enrich_dtc(c) for c in raw_scan.get("confirmed_dtcs", [])]
    pending   = [enrich_dtc(p) for p in raw_scan.get("pending_dtcs", [])]

    severities = {d["severity"] for d in confirmed + pending}
    system_status = ("critical" if "critical" in severities
                     else "warning" if severities else "healthy")

    return {
        "vehicle_id":     vin,
        "vin_info":       vin_info,
        "timestamp":      datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mil_active":     raw_scan.get("mil_active", False),
        "dtc_count":      len(confirmed) + len(pending),
        "confirmed_dtcs": confirmed,
        "pending_dtcs":   pending,
        "live_pids":      raw_scan.get("live_pids", {}),
        "freeze_frame":   raw_scan.get("freeze_frame", {}),
        "system_status":  system_status,
        "scan_summary":   build_scan_summary(
            raw_scan.get("mil_active", False), confirmed, pending
        ),
    }


def main():
    logger.info("--- OBD-CORTEX DATA LOGGER ---")
    logger.info(f"Scan Interval: {SCAN_INTERVAL}s | Heartbeat: {HEARTBEAT_INTERVAL}s")

    # -----------------------------------------------------------------------
    # CAN bus initialisation
    # -----------------------------------------------------------------------
    bus = None
    try:
        bus = init_can_bus()
    except RuntimeError as e:
        logger.error(f"Hardware error: {e}")
        sys.exit(1)

    init_buffer()

    # -----------------------------------------------------------------------
    # ECU presence check -- retry up to 5 times before aborting
    # -----------------------------------------------------------------------
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

    # -----------------------------------------------------------------------
    # VIN retrieval and local decode
    # -----------------------------------------------------------------------
    try:
        vin = read_vin(bus)
        logger.info(f"VEHICLE VIN IDENTIFIED: {vin}")
    except RuntimeError as e:
        logger.error(str(e))
        shutdown_can_bus(bus)
        sys.exit(1)

    vin_info = decode_vin(vin)
    logger.info(f"VIN DECODED: brand={vin_info['brand']}, year={vin_info['year']}, "
                f"region={vin_info['region']}, wmi={vin_info['wmi']}")

    if not EDGE_SERVICE_URL:
        logger.error("Required environment variable EDGE_SERVICE_URL is missing.")
        shutdown_can_bus(bus)
        sys.exit(1)

    logger.info(f"Connected to Central API Server: {EDGE_SERVICE_URL}")

    # -----------------------------------------------------------------------
    # Initial provisioning (first boot)
    # -----------------------------------------------------------------------
    if not is_provisioned():
        logger.info("Device not provisioned. Initiating provisioning flow...")
        try:
            do_provision(vin, vin_info)
        except Exception as e:
            logger.error(f"Provisioning failed: {e}")
            shutdown_can_bus(bus)
            sys.exit(1)
    else:
        from core.config import DEVICE_ID
        logger.info(f"Device already provisioned (Device ID: {DEVICE_ID}).")

    # -----------------------------------------------------------------------
    # Probe which OBD-II PIDs this vehicle's ECU supports (once per session)
    # -----------------------------------------------------------------------
    logger.info("Probing ECU for supported OBD-II PIDs...")
    supported_pids = read_supported_pids(bus)
    logger.info(f"ECU supports {len(supported_pids)} monitored PIDs.")

    # -----------------------------------------------------------------------
    # Main diagnostic loop
    # -----------------------------------------------------------------------
    last_scan_state  = None
    last_heartbeat_time = 0.0

    try:
        while True:
            current_time = time.time()
            raw_scan = run_full_scan(bus, supported_pids)

            # If scan returns completely empty, check ECU is still reachable
            no_data = (
                not raw_scan.get("confirmed_dtcs")
                and not raw_scan.get("pending_dtcs")
                and not raw_scan.get("live_pids")
                and not raw_scan.get("mil_active")
            )
            if no_data:
                if not ping_ecu(bus):
                    logger.warning("ECU unreachable -- attempting CAN bus reconnection...")
                    shutdown_can_bus(bus)
                    try:
                        bus = init_can_bus()
                        # Re-probe supported PIDs after reconnection
                        supported_pids = read_supported_pids(bus)
                    except RuntimeError:
                        logger.error("CAN bus reconnection failed.")

            heartbeat_due = (current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL)
            state_changed = has_state_changed(raw_scan, last_scan_state)

            if state_changed or heartbeat_due:
                reason = "State Changed" if state_changed else "Heartbeat"
                logger.info(f"Triggering telemetry capture. Reason: {reason}")
                telemetry = build_telemetry_document(vin, vin_info, raw_scan)
                save_to_buffer(telemetry)

                flush_result = flush_to_cloud()

                if flush_result == "REPROVISION_REQUIRED":
                    # The HMAC secret on disk is stale. Wipe keys and re-provision
                    # in-process so the next flush uses the correct secret.
                    logger.warning("Automatic re-provisioning triggered by stale HMAC secret.")
                    clear_provisioning_keys()
                    try:
                        do_provision(vin, vin_info)
                        # Retry the flush immediately with the new secret
                        flush_to_cloud()
                    except Exception as e:
                        logger.error(f"Automatic re-provisioning failed: {e}. "
                                     "Ensure DEVICE_TOKEN in .env matches the admin dashboard.")

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
