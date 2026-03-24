#!/usr/bin/env python3
import os
import time
import can
import logging

# Configure Logging to write to a file AND the console
LOG_FILE = "/home/obdpi/obd-cortex/obd_car_data.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [OBD-CORTEX] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def setup_can_interface():
    """Configures the hardware for LIVE car data."""
    logging.info("CONFIG: Initializing MCP2515 hardware...")
    
    # Reset and configure interface
    os.system("sudo ip link set can0 down")
    time.sleep(1)
    
    # CRITICAL CHANGE: Removed 'loopback on' to allow real physical CAN traffic.
    # Standard OBD-II high-speed CAN runs at 500kbps.
    exit_code = os.system("sudo ip link set can0 up type can bitrate 500000")
    
    if exit_code == 0:
        logging.info("SUCCESS: can0 interface is UP and ready for the car.")
        return True
    else:
        logging.error("FAILURE: Could not setup can0.")
        return False

def read_live_car_data():
    """Listens continuously to the CAN bus and logs everything."""
    logging.info("TEST: System ready. Listening for live CAN traffic...")
    logging.info("ACTION: Turn on the car's ignition to start seeing data.")

    try:
        with can.interface.Bus(channel='can0', interface='socketcan') as bus:
            while True:
                # Listen for messages on the bus
                msg = bus.recv(1.0) 
                
                if msg is None:
                    continue # No message yet, keep waiting...

                # Log everything we receive directly to the file and console
                logging.info(f"RECEIVED: ID={hex(msg.arbitration_id)} Data={msg.data.hex().upper()}")

    except KeyboardInterrupt:
        logging.info("--- TEST STOPPED BY USER ---")
        return True
    except Exception as e:
        logging.error(f"ERROR: {e}")
        return False

def main():
    # Step 1: Hardware Setup
    if not setup_can_interface():
        return

    # Step 2: Continuous Logging Loop
    if read_live_car_data():
        logging.info("--- SYSTEM SHUTDOWN CLEANLY ---")
    else:
        logging.critical("--- SYSTEM FAILED ---")

if __name__ == "__main__":
    main()

