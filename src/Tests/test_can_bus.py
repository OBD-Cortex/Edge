import sys
import time
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Dynamically find the root directory of the Edge project
EDGE_ROOT = Path(__file__).resolve().parent
while EDGE_ROOT.name and not (EDGE_ROOT / "src").is_dir():
    EDGE_ROOT = EDGE_ROOT.parent

# Add src to python path so imports work perfectly regardless of where you run it from
sys.path.insert(0, str(EDGE_ROOT / "src"))

from core.can_interface import init_can_bus, shutdown_can_bus
from services.obd_scanner import ping_ecu, read_vin, run_full_scan

def main():
    logger.info("==================================================")
    logger.info("Starting Isolated CAN Bus Diagnostic Test")
    logger.info("==================================================")

    bus = None
    try:
        logger.info("[*] Initializing CAN Bus interface (can0)...")
        bus = init_can_bus()
        logger.info("[✓] CAN Bus initialized successfully.")

        logger.info("\n--- Phase 1: Raw ISO-TP OBD2 Validation ---")
        from test_raw_7e8 import test_raw_ping, test_raw_vin_request
        
        logger.info("[*] Executing Raw Ping...")
        test_raw_ping(bus)
        time.sleep(1)
        
        logger.info("[*] Executing Raw VIN Request with Flow Control...")
        test_raw_vin_request(bus)
        time.sleep(1)

        logger.info("\n--- Phase 2: High-Level Pipeline Diagnostic Test ---")
        logger.info("[*] Pinging Vehicle ECU (Service 01 PID 00)...")
        if ping_ecu(bus):
            logger.info("[✓] Vehicle ECU responded to ping.")
        else:
            logger.warning("[!] Vehicle ECU did not respond to ping. (Make sure ignition is ON)")
            
        logger.info("[*] Querying Vehicle VIN (Service 09 PID 02)...")
        try:
            vin = read_vin(bus)
            logger.info(f"[✓] Successfully read VIN: {vin}")
        except Exception as e:
            logger.error(f"[!] Failed to read VIN: {e}")

        logger.info("[*] Running Full Diagnostic Scan (MIL, Confirmed & Pending DTCs)...")
        try:
            scan_results = run_full_scan(bus)
            
            mil = "ON" if scan_results.get("mil_active") else "OFF"
            logger.info("[✓] Scan Complete:")
            logger.info(f"    - Check Engine Light (MIL): {mil}")
            
            confirmed = scan_results.get("confirmed_dtcs", [])
            logger.info(f"    - Confirmed DTCs ({len(confirmed)}):")
            if not confirmed:
                logger.info("      (None)")
            for dtc in confirmed:
                logger.info(f"      * {dtc}")
                
            pending = scan_results.get("pending_dtcs", [])
            logger.info(f"    - Pending DTCs ({len(pending)}):")
            if not pending:
                logger.info("      (None)")
            for dtc in pending:
                logger.info(f"      * {dtc}")
                
        except Exception as e:
            logger.error(f"[!] Diagnostic scan failed: {e}")

    except Exception as e:
        logger.error(f"[!] Fatal Error: {e}")
    finally:
        if bus:
            logger.info("[*] Shutting down CAN bus interface...")
            shutdown_can_bus(bus)
            logger.info("==================================================")
            logger.info("Test Completed.")

if __name__ == "__main__":
    main()
