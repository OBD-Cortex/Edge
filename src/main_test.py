import os
import sys
import time
import argparse
import datetime
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

from core.telemetry_buffer import init_buffer, save_to_buffer, flush_to_cloud
from core.can_interface import init_can_bus
import core.config

def print_menu():
    print("\n==================================================")
    print(" OBD-Cortex Edge Performance Evaluation Suite")
    print("==================================================")
    print("1. Test CAN Bus Latency (PID Polling)")
    print("2. Test Offline SQLite Buffer I/O Throughput")
    print("3. Test Cloud Sync Latency (Edge-Service)")
    print("4. Run All Essential Tests")
    print("5. Exit")
    print("==================================================")

def test_can_latency():
    print("\n[*] Running CAN Bus Latency Test...")
    try:
        # We test with loopback since we might not be connected to a real car,
        # but the interface initializes the SocketCAN channel.
        # This just times the instantiation and basic filter setup.
        start_time = time.time()
        bus = init_can_bus()
        end_time = time.time()
        
        if bus:
            bus.shutdown()
        latency_ms = (end_time - start_time) * 1000
        print(f"    [✓] CAN Interface Init Latency: {latency_ms:.2f} ms")
        
        # If connected to a real car, we could test query_live_pids here.
        # Since this is a general test script, we just note the setup overhead.
        print("    [!] For live PID polling latency, ensure device is connected to OBD-II port.")
        return latency_ms
    except Exception as e:
        print(f"    [✗] CAN Interface test failed. Is can0 interface up? Error: {e}")
        return None

def test_sqlite_throughput():
    print("\n[*] Running SQLite Buffer I/O Test...")
    init_buffer()
    
    # Create 10 dummy snapshots
    snapshots = []
    for i in range(10):
        snapshots.append({
            "vehicle_id": "TEST_VIN_123",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "mil_active": False,
            "dtc_count": 0,
            "confirmed_dtcs": [],
            "pending_dtcs": [],
            "system_status": "healthy",
            "scan_summary": f"Performance buffer test {i}"
        })

    start_time = time.time()
    for snap in snapshots:
        save_to_buffer(snap)
    end_time = time.time()
    
    total_time_ms = (end_time - start_time) * 1000
    avg_insert_ms = total_time_ms / len(snapshots)
    print(f"    [✓] Buffered {len(snapshots)} records in {total_time_ms:.2f} ms")
    print(f"    [✓] Average insert latency: {avg_insert_ms:.2f} ms per record")
    return avg_insert_ms

def test_cloud_sync_latency():
    print("\n[*] Running Cloud Sync Latency Test...")
    edge_service_url = os.getenv("EDGE_SERVICE_URL")
    if not edge_service_url:
        print("    [✗] EDGE_SERVICE_URL not set in environment.")
        return None

    # Buffer a single record specifically for this test
    init_buffer()
    test_snapshot = {
        "vehicle_id": "TEST_VIN_123",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mil_active": False,
        "dtc_count": 0,
        "confirmed_dtcs": [],
        "pending_dtcs": [],
        "system_status": "healthy",
        "scan_summary": "Cloud Sync Latency Test Snapshot"
    }
    save_to_buffer(test_snapshot)

    print(f"    [*] Attempting to flush buffer to: {edge_service_url}")
    start_time = time.time()
    try:
        result = flush_to_cloud()
        end_time = time.time()
        
        if result == "REPROVISION_REQUIRED":
            print("    [✗] Server rejected HMAC signature. Re-provisioning required.")
            return None
        
        latency_ms = (end_time - start_time) * 1000
        print(f"    [✓] Cloud sync completed successfully in {latency_ms:.2f} ms")
        return latency_ms
    except Exception as e:
        print(f"    [✗] Cloud sync failed: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Edge Performance Testing")
    parser.add_argument("--auto", choices=['can', 'sqlite', 'cloud', 'all'], help="Run specific test automatically without interactive menu")
    args = parser.parse_args()

    if args.auto:
        if args.auto == 'can': test_can_latency()
        elif args.auto == 'sqlite': test_sqlite_throughput()
        elif args.auto == 'cloud': test_cloud_sync_latency()
        elif args.auto == 'all':
            test_can_latency()
            test_sqlite_throughput()
            test_cloud_sync_latency()
        sys.exit(0)

    while True:
        print_menu()
        choice = input("Select an option (1-5): ").strip()
        
        if choice == '1':
            test_can_latency()
        elif choice == '2':
            test_sqlite_throughput()
        elif choice == '3':
            test_cloud_sync_latency()
        elif choice == '4':
            test_can_latency()
            test_sqlite_throughput()
            test_cloud_sync_latency()
        elif choice == '5':
            print("Exiting...")
            break
        else:
            print("Invalid selection. Please enter a number between 1 and 5.")

if __name__ == "__main__":
    main()
