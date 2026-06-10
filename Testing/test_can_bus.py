import sys
import time
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add src to python path so imports work
EDGE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EDGE_ROOT / "src"))

from core.can_interface import init_can_bus, shutdown_can_bus
from services.obd_scanner import ping_ecu, read_vin, run_full_scan

def main():
    print("==================================================")
    print("Starting Isolated CAN Bus Diagnostic Test")
    print("==================================================")

    bus = None
    try:
        print("[*] Initializing CAN Bus interface (can0)...")
        bus = init_can_bus()
        print("[✓] CAN Bus initialized successfully.")

        print("\n[*] Pinging Vehicle ECU (Service 01 PID 00)...")
        if ping_ecu(bus):
            print("[✓] Vehicle ECU responded to ping.")
        else:
            print("[!] Vehicle ECU did not respond to ping. (Make sure ignition is ON)")
            
        print("\n[*] Querying Vehicle VIN (Service 09 PID 02)...")
        try:
            vin = read_vin(bus)
            print(f"[✓] Successfully read VIN: {vin}")
        except Exception as e:
            print(f"[!] Failed to read VIN: {e}")

        print("\n[*] Running Full Diagnostic Scan (MIL, Confirmed & Pending DTCs)...")
        try:
            scan_results = run_full_scan(bus)
            
            mil = "ON" if scan_results.get("mil_active") else "OFF"
            print(f"[✓] Scan Complete:")
            print(f"    - Check Engine Light (MIL): {mil}")
            
            confirmed = scan_results.get("confirmed_dtcs", [])
            print(f"    - Confirmed DTCs ({len(confirmed)}):")
            if not confirmed:
                print("      (None)")
            for dtc in confirmed:
                print(f"      * {dtc}")
                
            pending = scan_results.get("pending_dtcs", [])
            print(f"    - Pending DTCs ({len(pending)}):")
            if not pending:
                print("      (None)")
            for dtc in pending:
                print(f"      * {dtc}")
                
        except Exception as e:
            print(f"[!] Diagnostic scan failed: {e}")

    except Exception as e:
        print(f"\n[!] Fatal Error: {e}")
    finally:
        if bus:
            print("\n[*] Shutting down CAN bus interface...")
            shutdown_can_bus(bus)
            print("==================================================")
            print("Test Completed.")

if __name__ == "__main__":
    main()
