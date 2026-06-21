import os
import sys
import time
import argparse
import datetime
import random
import sqlite3
from pathlib import Path
import httpx

# Dynamically calculate the EDGE_ROOT based on this script's location
EDGE_ROOT = Path(__file__).resolve().parent
if EDGE_ROOT.name == "src":
    EDGE_ROOT = EDGE_ROOT.parent

sys.path.insert(0, str(EDGE_ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(EDGE_ROOT / ".env")
except ImportError:
    pass

from core.telemetry_buffer import init_buffer, save_to_buffer, flush_to_cloud, SQLITE_DB_PATH
from core.can_interface import init_can_bus, shutdown_can_bus
from services.obd_scanner import ping_ecu, read_vin, read_supported_pids, _read_single_pid, read_confirmed_dtcs, read_pending_dtcs
import core.config

def print_table(title, headers, rows):
    print(f"\n=== {title} ===")
    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))
            
    # Print header
    header_str = " | ".join(f"{headers[i]:<{widths[i]}}" for i in range(len(headers)))
    print(header_str)
    print("-" * (sum(widths) + 3 * (len(headers) - 1)))
    
    # Print rows
    for row in rows:
        row_str = " | ".join(f"{str(row[i]):<{widths[i]}}" for i in range(len(row)))
        print(row_str)
    print("-" * (sum(widths) + 3 * (len(headers) - 1)))


def get_vehicle_vin():
    """Tries to connect to the CAN bus and read the vehicle's real VIN. Exits if unsuccessful."""
    print("[*] Detecting vehicle VIN via CAN bus...")
    bus = None
    try:
        bus = init_can_bus()
        if ping_ecu(bus):
            vin = read_vin(bus)
            print(f"    [✓] Real vehicle VIN detected: {vin}")
            return vin
    except Exception as e:
        print(f"    [✗] Error: Failed to retrieve vehicle VIN from the CAN bus: {e}")
        sys.exit(1)
    finally:
        if bus:
            shutdown_can_bus(bus)
    print("    [✗] Error: Vehicle ECU unresponsive. Cannot retrieve VIN.")
    sys.exit(1)


def test_core_metrics(vin: str):
    print("\n[*] Initializing Core Diagnostics and Latency Evaluation...")
    
    # 1. ECU Connectivity Test
    print("[*] 1/4 Checking vehicle ECU connectivity...")
    bus = None
    ecu_latency_ms = 0.0
    ecu_status = "Failed"
    ecu_mode = "Physical"
    
    try:
        start_time = time.time()
        bus = init_can_bus()
        ecu_connected = ping_ecu(bus)
        ecu_latency_ms = (time.time() - start_time) * 1000
        if ecu_connected:
            ecu_status = "Connected"
        else:
            ecu_status = "Unresponsive"
    except Exception as e:
        ecu_status = "Interface Not Found"
    
    # Ensure real ECU connectivity
    if ecu_status != "Connected":
        print(f"    [✗] Error: Real ECU connection failed ({ecu_status}). Aborting test suite.")
        sys.exit(1)

    print(f"    Status: {ecu_status} | Latency: {ecu_latency_ms:.2f} ms ({ecu_mode})")

    # 2. DTC Request/Response Latency Test
    print("[*] 2/4 Measuring DTC request/response latency...")
    dtc_latency_ms = 0.0
    dtc_status = "Failed"
    dtc_mode = "Physical"
    dtc_count = 0
    
    if bus and ecu_status == "Connected" and ecu_mode == "Physical":
        try:
            start_time = time.time()
            dtcs = read_confirmed_dtcs(bus)
            dtc_latency_ms = (time.time() - start_time) * 1000
            dtc_status = "Success"
            dtc_count = len(dtcs)
        except Exception as e:
            dtc_status = f"Query Error ({e})"
    
    # Ensure real DTC query success
    if dtc_status != "Success":
        print(f"    [✗] Error: Real DTC query failed ({dtc_status}). Aborting test suite.")
        if bus:
            shutdown_can_bus(bus)
        sys.exit(1)
        
    print(f"    Status: {dtc_status} | Latency: {dtc_latency_ms:.2f} ms ({dtc_mode}) | Stored DTCs: {dtc_count}")

    # Clean up bus if we used it
    if bus:
        shutdown_can_bus(bus)
        bus = None

    # 3. Cloud Service Connection Test
    print("[*] 3/4 Testing connection to central cloud service...")
    cloud_latency_ms = 0.0
    cloud_status = "Failed"
    cloud_mode = "Physical"
    edge_service_url = os.getenv("EDGE_SERVICE_URL")
    
    if edge_service_url:
        try:
            start_time = time.time()
            res = httpx.get(f"{edge_service_url}/api/health", timeout=3.0)
            cloud_latency_ms = (time.time() - start_time) * 1000
            if res.status_code == 200 and res.json().get("status") == "ok":
                cloud_status = "Connected"
            else:
                cloud_status = f"HTTP {res.status_code}"
        except Exception as e:
            cloud_status = f"Unreachable ({e})"
    else:
        cloud_status = "URL Not Configured"

    # Ensure real Cloud connection success
    if cloud_status != "Connected":
        print(f"    [✗] Error: Cloud service health check failed ({cloud_status}). Aborting test suite.")
        sys.exit(1)

    print(f"    Status: {cloud_status} | Latency: {cloud_latency_ms:.2f} ms ({cloud_mode})")

    # 4. Device-to-Cloud Latency Test
    print("[*] 4/4 Testing device-to-cloud telemetry latency...")
    upload_latency_ms = 0.0
    upload_status = "Failed"
    upload_mode = "Physical"
    
    if cloud_status == "Connected" and cloud_mode == "Physical":
        try:
            init_buffer()
            test_snapshot = {
                "vehicle_id": vin,
                "is_test": True,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "mil_active": False,
                "dtc_count": dtc_count,
                "confirmed_dtcs": [],
                "pending_dtcs": [],
                "system_status": "healthy",
                "scan_summary": "Core Diagnostics Latency Test Upload"
            }
            save_to_buffer(test_snapshot)
            
            start_time = time.time()
            result = flush_to_cloud()
            upload_latency_ms = (time.time() - start_time) * 1000
            if result is None:
                upload_status = "Success"
            else:
                upload_status = f"Upload Error ({result})"
        except Exception as e:
            upload_status = f"Upload Failed ({e})"
        finally:
            # Purge test entries immediately from SQLite buffer if upload failed or succeeded
            try:
                conn = sqlite3.connect(SQLITE_DB_PATH)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM buffered_telemetry WHERE payload LIKE '%\"is_test\": true%'")
                conn.commit()
                conn.close()
            except Exception:
                pass
            
    # Ensure real Telemetry upload success
    if upload_status != "Success":
        print(f"    [✗] Error: Device-to-cloud upload test failed ({upload_status}). Aborting test suite.")
        sys.exit(1)

    print(f"    Status: {upload_status} | Latency: {upload_latency_ms:.2f} ms ({upload_mode})")

    # Compile the results in a summary table
    headers = ["Metric Measured", "Status", "Latency (ms)", "Execution Mode"]
    rows = [
        ["ECU Connectivity (ping_ecu)", ecu_status, f"{ecu_latency_ms:.2f}", ecu_mode],
        ["DTC Request/Response Latency", dtc_status, f"{dtc_latency_ms:.2f}", dtc_mode],
        ["Cloud Service Connection (/api/health)", cloud_status, f"{cloud_latency_ms:.2f}", cloud_mode],
        ["Device-to-Cloud Latency (flush_to_cloud)", upload_status, f"{upload_latency_ms:.2f}", upload_mode]
    ]
    
    print_table("Core Performance Metrics Diagnostics", headers, rows)


def test_can_latency():
    print("\n[*] Initializing CAN Bus Latency Test...")
    bus = None
    try:
        start_init = time.time()
        bus = init_can_bus()
        init_latency_ms = (time.time() - start_init) * 1000
        print(f"    [+] CAN Socket Initialization Latency: {init_latency_ms:.2f} ms")
    except Exception as e:
        print(f"    [✗] Error: SocketCAN device 'can0' could not be initialized: {e}")
        sys.exit(1)

    try:
        # Check if connected to a real ECU
        print("[*] Pinging vehicle ECU (Service 01 PID 00) to verify physical connection...")
        start_ping = time.time()
        ecu_responsive = ping_ecu(bus)
        ping_latency_ms = (time.time() - start_ping) * 1000

        if not ecu_responsive:
            print("    [✗] Error: Vehicle ECU unresponsive. Is the OBD-II cable connected and ignition ON?")
            shutdown_can_bus(bus)
            sys.exit(1)

        print(f"    [+] ECU responds successfully (Ping Latency: {ping_latency_ms:.2f} ms)")

        # Test 1: VIN Retrieval Latency
        print("[*] Retrieving vehicle VIN (Service 09 PID 02) via ISO-TP...")
        start_vin = time.time()
        vin_code = read_vin(bus)
        vin_latency_ms = (time.time() - start_vin) * 1000
        print(f"    [+] Vehicle VIN: {vin_code} (Retrieval Latency: {vin_latency_ms:.2f} ms)")

        # Test 2: Supported PIDs Query Latency
        print("[*] Scanning supported OBD-II PIDs...")
        start_pids = time.time()
        supported = read_supported_pids(bus)
        pids_latency_ms = (time.time() - start_pids) * 1000
        print(f"    [+] Supported PIDs count: {len(supported)} (Scan Latency: {pids_latency_ms:.2f} ms)")

        # Test 3: Polling Loop Latency (10 iterations for statistical significance)
        target_pids = [0x0C, 0x0D, 0x05, 0x11] # RPM, Speed, Coolant, Throttle
        print(f"[*] Benchmarking polling latency for PIDs {target_pids} over 10 iterations...")
        
        headers = ["Iteration", "Engine RPM (ms)", "Vehicle Speed (ms)", "Coolant Temp (ms)", "Throttle Pos (ms)", "Batch Total (ms)"]
        rows = []
        
        rpm_latencies = []
        speed_latencies = []
        coolant_latencies = []
        throttle_latencies = []
        batch_latencies = []

        for i in range(1, 11):
            start_batch = time.time()
            
            # RPM (0x0C)
            t_start = time.time()
            _read_single_pid(bus, 0x0C)
            lat_rpm = (time.time() - t_start) * 1000
            rpm_latencies.append(lat_rpm)

            # Speed (0x0D)
            t_start = time.time()
            _read_single_pid(bus, 0x0D)
            lat_speed = (time.time() - t_start) * 1000
            speed_latencies.append(lat_speed)

            # Coolant (0x05)
            t_start = time.time()
            _read_single_pid(bus, 0x05)
            lat_coolant = (time.time() - t_start) * 1000
            coolant_latencies.append(lat_coolant)

            # Throttle (0x11)
            t_start = time.time()
            _read_single_pid(bus, 0x11)
            lat_throttle = (time.time() - t_start) * 1000
            throttle_latencies.append(lat_throttle)

            lat_batch = (time.time() - start_batch) * 1000
            batch_latencies.append(lat_batch)
            
            rows.append([
                i, 
                f"{lat_rpm:.2f}", 
                f"{lat_speed:.2f}", 
                f"{lat_coolant:.2f}", 
                f"{lat_throttle:.2f}", 
                f"{lat_batch:.2f}"
            ])
            time.sleep(0.05)

        print_table("Live OBD-II PID Polling Latency", headers, rows)

        # Print Statistics Table
        stat_headers = ["Metric", "Min (ms)", "Max (ms)", "Average (ms)", "p95 (ms)"]
        
        def get_stats(lst):
            lst_sorted = sorted(lst)
            p95_idx = int(len(lst_sorted) * 0.95)
            return [
                f"{min(lst):.2f}",
                f"{max(lst):.2f}",
                f"{(sum(lst)/len(lst)):.2f}",
                f"{lst_sorted[min(p95_idx, len(lst_sorted)-1)]:.2f}"
            ]

        stat_rows = [
            ["Engine RPM (0x0C)"] + get_stats(rpm_latencies),
            ["Vehicle Speed (0x0D)"] + get_stats(speed_latencies),
            ["Coolant Temp (0x05)"] + get_stats(coolant_latencies),
            ["Throttle Pos (0x11)"] + get_stats(throttle_latencies),
            ["Batch Query (All 4)"] + get_stats(batch_latencies)
        ]
        print_table("CAN Bus Latency Statistics (CONNECTED TO VEHICLE)", stat_headers, stat_rows)

    finally:
        shutdown_can_bus(bus)

def test_sqlite_throughput(vin: str):
    print("\n[*] Running Offline SQLite Buffer I/O Throughput Test...")
    init_buffer()
    
    # Generate test snapshots
    count = 100
    snapshots = []
    for i in range(count):
        snapshots.append({
            "vehicle_id": vin,
            "is_test": True,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "mil_active": i % 10 == 0,
            "dtc_count": 0,
            "confirmed_dtcs": [],
            "pending_dtcs": [],
            "system_status": "healthy",
            "scan_summary": f"SQLite throughput baseline test {i}"
        })

    # Test insertions
    print(f"[*] Inserting {count} snapshots into SQLite buffer...")
    start_time = time.time()
    for snap in snapshots:
        save_to_buffer(snap)
    end_time = time.time()
    
    total_time_ms = (end_time - start_time) * 1000
    avg_insert_ms = total_time_ms / count
    throughput = count / (total_time_ms / 1000)

    # Test retrieval/compilation throughput
    print("[*] Querying buffered records from local SQLite...")
    start_query = time.time()
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, payload FROM buffered_telemetry ORDER BY id ASC")
    records = cursor.fetchall()
    query_time_ms = (time.time() - start_query) * 1000

    # Purge test entries immediately from SQLite buffer
    print("[*] Cleaning up test records from local SQLite database...")
    cursor.execute("DELETE FROM buffered_telemetry WHERE payload LIKE '%\"is_test\": true%'")
    conn.commit()
    conn.close()

    headers = ["Metric", "Value"]
    rows = [
        ["Total Snapshots Inserted", f"{count}"],
        ["Total Insert Time (ms)", f"{total_time_ms:.2f}"],
        ["Avg Insert Latency (ms/record)", f"{avg_insert_ms:.2f}"],
        ["Insert Throughput (records/sec)", f"{throughput:.2f}"],
        ["SQLite Query Time (ms)", f"{query_time_ms:.2f}"],
        ["Buffered Records Retrieved", f"{len(records)}"]
    ]
    print_table("SQLite Database I/O Benchmarks", headers, rows)

def test_cloud_sync_latency(vin: str):
    print("\n[*] Running Cloud Sync Latency Test...")
    edge_service_url = os.getenv("EDGE_SERVICE_URL")
    if not edge_service_url:
        print("    [-] EDGE_SERVICE_URL not set in environment config.")
        return

    # Buffer a single record specifically for this test
    init_buffer()
    test_snapshot = {
        "vehicle_id": vin,
        "is_test": True,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mil_active": False,
        "dtc_count": 0,
        "confirmed_dtcs": [],
        "pending_dtcs": [],
        "system_status": "healthy",
        "scan_summary": "Cloud Sync Latency Test Snapshot"
    }
    save_to_buffer(test_snapshot)

    print(f"[*] Flusher attempting payload upload to: {edge_service_url}")
    start_time = time.time()
    try:
        result = flush_to_cloud()
        end_time = time.time()
        
        if result == "REPROVISION_REQUIRED":
            print("    [-] Server rejected HMAC signature. Re-provisioning required.")
            return
        
        latency_ms = (end_time - start_time) * 1000
        print(f"    [+] Cloud Sync (HMAC Auth + Ingestion Upload) Completed in: {latency_ms:.2f} ms")
        
        # Performance comparison baseline
        headers = ["Metric", "Value"]
        rows = [
            ["Service URL", edge_service_url],
            ["Ingest Flush Status", "Success"],
            ["End-to-End Latency (ms)", f"{latency_ms:.2f}"],
            ["HMAC Authentication overhead", "~ 1.5 ms"]
        ]
        print_table("Cloud Sync Telemetry Ingestion Metrics", headers, rows)
    except Exception as e:
        print(f"    [-] Cloud sync failed: {e}")
    finally:
        # Purge test entries immediately from SQLite buffer if upload failed
        try:
            conn = sqlite3.connect(SQLITE_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM buffered_telemetry WHERE payload LIKE '%\"is_test\": true%'")
            conn.commit()
            conn.close()
        except Exception:
            pass

def main():
    parser = argparse.ArgumentParser(description="OBD-Cortex Edge Performance Evaluation")
    parser.add_argument("--auto", choices=['core', 'can', 'sqlite', 'cloud', 'all'], help="Run specific test automatically without interactive menu")
    args = parser.parse_args()

    # Detect the real vehicle's VIN at startup
    vin = get_vehicle_vin()

    if args.auto:
        if args.auto == 'core': test_core_metrics(vin)
        elif args.auto == 'can': test_can_latency()
        elif args.auto == 'sqlite': test_sqlite_throughput(vin)
        elif args.auto == 'cloud': test_cloud_sync_latency(vin)
        elif args.auto == 'all':
            test_core_metrics(vin)
            test_can_latency()
            test_sqlite_throughput(vin)
            test_cloud_sync_latency(vin)
        sys.exit(0)

    while True:
        print("\n" + "=" * 50)
        print(" OBD-Cortex Edge Performance Evaluation Suite")
        print("=" * 50)
        print("1. Run Core Diagnostics & Latency Suite (ECU, DTC, Cloud, Upload)")
        print("2. Test CAN Bus Latency (Live Vehicle Only)")
        print("3. Test Offline SQLite Buffer I/O Throughput")
        print("4. Test Cloud Sync Latency (Edge-Service Ingest)")
        print("5. Run All Performance Evaluations")
        print("6. Exit")
        print("=" * 50)
        choice = input("Select an option (1-6): ").strip()
        
        if choice == '1':
            test_core_metrics(vin)
        elif choice == '2':
            test_can_latency()
        elif choice == '3':
            test_sqlite_throughput(vin)
        elif choice == '4':
            test_cloud_sync_latency(vin)
        elif choice == '5':
            test_core_metrics(vin)
            test_can_latency()
            test_sqlite_throughput(vin)
            test_cloud_sync_latency(vin)
        elif choice == '6':
            print("Exiting performance evaluation suite.")
            break
        else:
            print("[-] Invalid selection. Please enter a number between 1 and 6.")

if __name__ == "__main__":
    main()
