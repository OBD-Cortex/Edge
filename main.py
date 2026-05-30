#!/usr/bin/env python3
"""
Embedded-Automotive-Edge Gateway Logger
OBD-Cortex IoT Telemetry Streamer for Raspberry Pi 4.

Orchestrates CAN bus reading, DTC diagnostics, local buffering, and cloud syncing.
"""

import sys
import time
import datetime
from config import (
    MONGO_URI,
    DEVICE_TOKEN,
    SCAN_INTERVAL,
    HEARTBEAT_INTERVAL,
    RECONNECT_COOLDOWN,
    TEST_MODE,
    OFFLINE_MODE
)
from can_interface import init_can_bus, shutdown_can_bus
from obd_scanner import read_vin, run_full_scan
from dtc_sanitizer import enrich_dtc, build_scan_summary, has_state_changed
from telemetry_buffer import init_buffer, save_to_buffer, flush_to_mongodb
from cloud_sync import connect_to_mongodb, register_device, decode_vin

def run_loopback_test(bus, is_simulated):
    """
    Original loopback test mechanism. Listens on can0 for '123#DEADBEEF'.
    """
    print("TEST: System ready. Waiting for manual trigger...")
    if is_simulated or not bus:
        print("[!] ERROR: Loopback test requires a physical SocketCAN 'can0' interface.")
        sys.exit(1)

    try:
        while True:
            msg = bus.recv(timeout=1.0)
            if msg is None:
                continue

            if msg.arbitration_id == 0x123 and msg.data.hex().upper() == "DEADBEEF":
                print(f"\nRECEIVED: ID=0x{msg.arbitration_id:x} Data={msg.data.hex().upper()}")
                print("PASSED: Manual test confirmed!")
                print("--- SYSTEM HEALTHY: GoodBye! ---")
                sys.exit(0)
    except KeyboardInterrupt:
        print("\n🛑 Loopback test cancelled.")
        sys.exit(1)

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
    bus, is_simulated = init_can_bus()
    init_buffer()

    if TEST_MODE:
        run_loopback_test(bus, is_simulated)
        return

    # 2. Connect to MongoDB (initial connection)
    mongo_client, col_telemetry, col_devices = connect_to_mongodb(MONGO_URI)
    if mongo_client:
        print("[✓] Connected to MongoDB Cloud Database.")
    else:
        print("[!] Local offline logging mode active. Telemetry will be buffered in SQLite.")

    # 3. Read Vehicle Identification Number (VIN)
    vin = read_vin(bus, is_simulated)
    print(f"🚗 VEHICLE VIN IDENTIFIED: {vin}")

    # 4. NHTSA Decode vehicle info and register device
    brand, model, year = decode_vin(vin)
    if mongo_client:
        register_device(col_devices, DEVICE_TOKEN, vin, brand, model, year)

    # 5. Core Streaming loop
    last_scan_state = None
    last_heartbeat_time = 0.0
    last_reconnect_time = 0.0

    try:
        while True:
            current_time = time.time()
            
            # Reconnection logic if MongoDB is offline
            if not mongo_client and not OFFLINE_MODE:
                if current_time - last_reconnect_time > RECONNECT_COOLDOWN:
                    print("🔄 [Database] Attempting background reconnection to MongoDB Atlas...")
                    last_reconnect_time = current_time
                    mongo_client, col_telemetry, col_devices = connect_to_mongodb(MONGO_URI)
                    if mongo_client:
                        print("[✓] Reconnection Successful! Cloud database is online.")
                        register_device(col_devices, DEVICE_TOKEN, vin, brand, model, year)

            # A. Run full diagnostic scan
            raw_scan = run_full_scan(bus, is_simulated)

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
                if mongo_client and col_telemetry:
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
    finally:
        print("\n--- SHUTTING DOWN OBD-CORTEX LOGGER ---")
        shutdown_can_bus(bus)
        if mongo_client:
            try:
                mongo_client.close()
                print("[Database] MongoDB connection pool closed.")
            except Exception as e:
                print(f"[!] Error closing MongoDB connection: {e}")

if __name__ == "__main__":
    main()
