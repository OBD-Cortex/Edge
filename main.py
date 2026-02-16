#!/usr/bin/env python3
import os
import time
import can
import logging

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [OBD-CORTEX] - %(levelname)s - %(message)s'
)

def setup_can_interface():
    """Configures the hardware in Loopback Mode."""
    logging.info("CONFIG: Initializing MCP2515 hardware...")
    
    # Reset and configure interface
    os.system("sudo ip link set can0 down")
    time.sleep(1)
    # Loopback ON allows you to see what you send from the terminal
    exit_code = os.system("sudo ip link set can0 up type can bitrate 500000 loopback on")
    
    if exit_code == 0:
        logging.info("SUCCESS: can0 interface is UP.")
        return True
    else:
        logging.error("FAILURE: Could not setup can0.")
        return False

def wait_for_manual_trigger():
    """Waits indefinitely for a specific CAN message from the terminal."""
    logging.info("TEST: System ready. Waiting for manual trigger...")
    logging.info("ACTION: Open a new terminal and run: cansend can0 123#DEADBEEF")

    try:
        # The 'with' block handles the connection cleanup automatically
        with can.interface.Bus(channel='can0', interface='socketcan') as bus:
            while True:
                # Wait 1 second for a message, then loop
                msg = bus.recv(1.0) 
                
                if msg is None:
                    continue # No message yet, keep waiting...

                # Log what we received
                logging.info(f"RECEIVED: ID={hex(msg.arbitration_id)} Data={msg.data.hex().upper()}")

                # Check if it matches our "Secret Handshake"
                if msg.arbitration_id == 0x123 and msg.data.hex().upper() == "DEADBEEF":
                    logging.info("PASSED: Manual test confirmed!")
                    return True

    except Exception as e:
        logging.error(f"ERROR: {e}")
        return False

def main():
    # Step 1: Hardware Setup
    if not setup_can_interface():
        return

    # Step 2: Wait for YOU to test it
    if wait_for_manual_trigger():
        logging.info("--- SYSTEM HEALTHY: GoodBye! ---")
        
        # Step 3: Standby Loop (Placeholder for future code)
        # while True:
        #     time.sleep(1000) 
    else:
        logging.critical("--- SYSTEM FAILED ---")

if __name__ == "__main__":
    main()
