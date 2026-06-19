import sys
import time
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add src to python path so imports work perfectly
SRC_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_ROOT))

import can
from core.can_interface import init_can_bus, shutdown_can_bus, clear_buffer
from core.config import CAN_PADDING_BYTE

def test_raw_ping(bus):
    """Sends a raw Service 01 PID 00 ping and waits for any 0x7E8 response."""
    pad = CAN_PADDING_BYTE
    pad_str = f"{pad:02X} {pad:02X} {pad:02X} {pad:02X} {pad:02X}"
    logger.info(f"[*] Sending raw OBD-II Ping (0x7DF: 02 01 00 {pad_str})...")
    msg = can.Message(
        arbitration_id=0x7DF,
        data=[0x02, 0x01, 0x00, pad, pad, pad, pad, pad],
        is_extended_id=False
    )
    bus.send(msg)
    
    start = time.time()
    while time.time() - start < 2.0:
        response = bus.recv(timeout=0.5)
        if response:
            if response.arbitration_id == 0x7E8:
                logger.info(f"[✓] Received 0x7E8 response: {response.data.hex(' ')}")
                return True
            else:
                logger.info(f"[*] Received other response 0x{response.arbitration_id:X}: {response.data.hex(' ')}")
    logger.warning("[!] Timed out waiting for 0x7E8 response.")
    return False

def test_raw_vin_request(bus):
    """Sends a raw Service 09 PID 02 VIN request, replies with Flow Control (0x30), and captures the rest."""
    pad = CAN_PADDING_BYTE
    pad_str = f"{pad:02X} {pad:02X} {pad:02X} {pad:02X} {pad:02X}"
    logger.info(f"[*] Sending raw VIN Request (0x7DF: 02 09 02 {pad_str})...")
    msg = can.Message(
        arbitration_id=0x7DF,
        data=[0x02, 0x09, 0x02, pad, pad, pad, pad, pad],
        is_extended_id=False
    )
    bus.send(msg)
    
    start = time.time()
    first_frame_received = False
    
    while time.time() - start < 2.0:
        response = bus.recv(timeout=0.5)
        if response and response.arbitration_id == 0x7E8:
            logger.info(f"[✓] Received 0x7E8 response: {response.data.hex(' ')}")
            
            # Check if this is a First Frame (starts with 0x10)
            if response.data[0] & 0xF0 == 0x10:
                logger.info("[*] It's a First Frame! Sending Flow Control (0x30) to 0x7E0...")
                # Note: Flow Control MUST be sent to the physical request ID (0x7E0), 
                # NOT the broadcast ID (0x7DF) or the response ID (0x7E8).
                fc_msg = can.Message(
                    arbitration_id=0x7E0, 
                    data=[0x30, 0x00, 0x00, pad, pad, pad, pad, pad],
                    is_extended_id=False
                )
                bus.send(fc_msg)
                first_frame_received = True
                break
            else:
                return True
                
    if not first_frame_received:
        logger.warning("[!] Timed out waiting for First Frame.")
        return False
        
    # Now wait for Consecutive Frames (starting with 0x21, 0x22, etc.)
    logger.info("[*] Waiting for Consecutive Frames (0x21, 0x22, etc.)...")
    start = time.time()
    frames_collected = 0
    while time.time() - start < 2.0:
        response = bus.recv(timeout=0.5)
        if response and response.arbitration_id == 0x7E8:
            logger.info(f"[✓] Received Consecutive Frame: {response.data.hex(' ')}")
            frames_collected += 1
            if frames_collected >= 2: # Usually VIN takes 3 frames total (1 FF + 2 CFs)
                return True
                
    logger.warning("[!] Timed out waiting for all Consecutive Frames.")
    return False

def main():
    logger.info("==================================================")
    logger.info("Starting Raw CAN Bus Test (No ISO-TP Reassembly)")
    logger.info("==================================================")
    
    bus = None
    try:
        bus = init_can_bus()
        logger.info("[✓] CAN Bus initialized.")
        
        clear_buffer(bus)
        test_raw_ping(bus)
        
        time.sleep(1)
        
        clear_buffer(bus)
        test_raw_vin_request(bus)
        
    except Exception as e:
        logger.error(f"[!] Fatal Error: {e}")
    finally:
        if bus:
            shutdown_can_bus(bus)
            logger.info("==================================================")
            logger.info("Raw Test Completed.")

if __name__ == "__main__":
    main()
