#!/usr/bin/env python3
"""
Embedded-Automotive-Edge Gateway Logger
OBD-Cortex IoT Telemetry Streamer for Raspberry Pi 4.

Orchestrates CAN bus reading, DTC diagnostics, local buffering, and cloud syncing.
Enforces strict physical vehicle connectivity checks and retries during boot.
"""

import sys
import time
import datetime
from config import (
    MONGO_URI,
    DEVICE_TOKEN,
    SCAN_INTERVAL,
    HEARTBEAT_INTERVAL,
    RECONNECT_COOLDOWN
)
from can_interface import init_can_bus, shutdown_can_bus
from obd_scanner import ping_ecu, read_vin, run_full_scan
from dtc_sanitizer import enrich_dtc, build_scan_summary, has_state_changed
from telemetry_buffer import init_buffer, save_to_buffer, flush_to_mongodb
from cloud_sync import connect_to_mongodb, register_device, decode_vin

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
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
        "mil_active": raw_scan["mil_active"],
        "dtc_count": len(confirmed_enriched) + len(pending_enriched),
        "confirmed_dtcs": confirmed_enriched,
        "pending_dtcs": pending_enriched,
        "system_status": system_status,
        "scan_summary": scan_summary
    }

def main():
    print(f"--- OBD-CORTEX DATA LOGGER ---")
    print(f"Device Token: {DEVICE_TOKEN}")
    print(f"Scan Interval: {SCAN_INTERVAL}s")
    print(f"Heartbeat Interval: {HEARTBEAT_INTERVAL}s")
    print("Press Ctrl+C to exit.\n")

    # 1. Initialize hardware interfaces and local buffer
    bus = None
    try:
        bus = init_can_bus()
    except RuntimeError as e:
        print(f"[!] Hardware error: {e}")
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
            print(f"[!] Vehicle ECU is unresponsive. Waiting 2s before retry {attempt + 1}/{ping_attempts}...")
            time.sleep(2.0)

    if not ecu_found:
        print("[!] Error: Vehicle ECU did not respond. Is the ignition on?")
        shutdown_can_bus(bus)
        sys.exit(1)

    # 3. Read Vehicle Identification Number (VIN)
    # Internally retries up to 3 times
    try:
        vin = read_vin(bus)
        print(f"🚗 VEHICLE VIN IDENTIFIED: {vin}")
    except RuntimeError as e:
        print(f"[!] {e}")
        shutdown_can_bus(bus)
        sys.exit(1)

    # 4. Connect to MongoDB (initial connection)
    # Exits immediately at boot if connection is unreachable or configuration is missing
    if not MONGO_URI:
        print("[!] Error: Required environment variable MONGO_URI is missing.")
        shutdown_can_bus(bus)
        sys.exit(1)

    mongo_client, col_telemetry, col_devices = connect_to_mongodb(MONGO_URI)
    if mongo_client is None:
        print("[!] Error: Could not connect to MongoDB database at startup. Aborting.")
        shutdown_can_bus(bus)
        sys.exit(1)

    print("[✓] Connected to MongoDB Cloud Database.")

    # 5. NHTSA Decode vehicle info and register device
    brand, model, year = decode_vin(vin)
    register_device(col_devices, DEVICE_TOKEN, vin, brand, model, year)

    # 6. Core Streaming loop
    last_scan_state = None
    last_heartbeat_time = 0.0
    last_reconnect_time = 0.0

    try:
        while True:
            current_time = time.time()
            
            # Reconnection logic if MongoDB is offline
            if mongo_client is None:
                if current_time - last_reconnect_time > RECONNECT_COOLDOWN:
                    print("🔄 [Database] Attempting background reconnection to MongoDB Atlas...")
                    last_reconnect_time = current_time
                    mongo_client, col_telemetry, col_devices = connect_to_mongodb(MONGO_URI)
                    if mongo_client is not None:
                        print("[✓] Reconnection Successful! Cloud database is online.")
                        register_device(col_devices, DEVICE_TOKEN, vin, brand, model, year)

            # A. Run full diagnostic scan
            raw_scan = run_full_scan(bus)

            # B. Evaluate trigger conditions
            heartbeat_due = (current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL)
            state_changed = has_state_changed(raw_scan, last_scan_state)

            if state_changed or heartbeat_due:
                reason = "DTC State Changed" if state_changed else "Heartbeat Interval Elapsed"
                print(f"[!] Triggering telemetry capture. Reason: {reason}")
                
                # Assemble telemetry snapshot document
                telemetry = build_telemetry_document(vin, raw_scan)

                # Store snapshot in local SQLite buffer first (ensures zero data loss)
                save_to_buffer(telemetry)

                # Attempt to flush the SQLite buffer to MongoDB
                if col_telemetry is not None:
                    flush_to_mongodb(col_telemetry)
                    
                # Reset timers and state tracking
                last_scan_state = raw_scan
                last_heartbeat_time = current_time
            else:
                # Telemetry skipped because state is unchanged and heartbeat is not due
                pass

            time.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        print("\n[!] Logger process terminated by user.")
    except Exception as e:
        print(f"[!] Critical loop error: {e}")
    finally:
        print("\n--- SHUTTING DOWN OBD-CORTEX LOGGER ---")
        shutdown_can_bus(bus)
        if mongo_client is not None:
            try:
                mongo_client.close()
                print("[Database] MongoDB connection pool closed.")
            except Exception as e:
                print(f"[!] Error closing MongoDB connection: {e}")

if __name__ == "__main__":
    main()
