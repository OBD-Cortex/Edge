import time
import logging
from core.can_interface import send_obd_request, clear_buffer, recv_isotp_messages
from services.dtc_sanitizer import decode_dtc_bytes

logger = logging.getLogger(__name__)

def ping_ecu(bus) -> bool:
    """
    Pings the vehicle's ECU using standard OBD-II Service 01 PID 00.
    Returns True if any ECU responds (even with a Negative Response Code),
    confirming the CAN bus and ECU are alive and communicating.
    """
    if not bus:
        return False
    logger.info("OBD-II: Pinging vehicle ECU (Service 01 PID 00)...")
    
    clear_buffer(bus)
    success = send_obd_request(bus, 0x7DF, [0x02, 0x01, 0x00])
    if not success:
        return False
        
    # Give the ECU 1.0s to respond in case it is waking up from sleep
    payloads = recv_isotp_messages(bus, range(0x7E8, 0x7F0), timeout=1.0)
    
    for ecu_id, payload in payloads.items():
        # Any valid ISO-TP payload confirms the ECU is alive
        # Positive response starts with 0x41
        # Negative response starts with 0x7F
        if len(payload) > 0:
            logger.info(f"Vehicle ECU (0x{ecu_id:03X}) responded to ping with payload: {payload.hex()}")
            return True
            
    return False

def read_vin(bus) -> str:
    """
    Queries the vehicle's ECU via standard OBD-II PID 09 02 over CAN frame 0x7DF.
    Supports ISO-TP multi-frame reassembly.
    Retries up to 3 times before raising RuntimeError.
    """
    if not bus:
        raise RuntimeError("CAN bus is not initialized.")

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        logger.info(f"OBD-II: Querying ECU for vehicle VIN (Attempt {attempt}/{max_attempts})...")
        
        clear_buffer(bus)
        success = send_obd_request(bus, 0x7DF, [0x02, 0x09, 0x02])
        if not success:
            if attempt < max_attempts:
                time.sleep(1.0)
            continue

        try:
            payloads = recv_isotp_messages(bus, range(0x7E8, 0x7F0), timeout=3.0)
            for ecu_id, payload in payloads.items():
                if len(payload) >= 20 and payload[0] == 0x49 and payload[1] == 0x02:
                    # ISO-TP assembled payload starts with service byte (0x49)
                    # payload[0]: 0x49 (Service response)
                    # payload[1]: 0x02 (PID response)
                    # payload[2]: 0x01 (Number of data items)
                    # payload[3:20]: 17 bytes of VIN
                    vin = payload[3:20].decode('ascii', errors='ignore').strip()
                    if len(vin) == 17:
                        return vin

            logger.warning(f"OBD-II: VIN query timed out on attempt {attempt}.")
        except Exception as e:
            logger.error(f"OBD-II: Error reading VIN on attempt {attempt}: {e}")
        
        if attempt < max_attempts:
            time.sleep(1.0)

    raise RuntimeError("Failed to retrieve vehicle VIN after retries.")

def read_mil_status(bus):
    """
    Queries Service 01 PID 01 to read MIL status (check engine light) and stored DTC count.
    Aggregates checks and counts across all responding ECUs (0x7E8–0x7EF).
    Returns (mil_active: bool, dtc_count: int).
    """
    if not bus:
        return False, 0

    clear_buffer(bus)
    success = send_obd_request(bus, 0x7DF, [0x02, 0x01, 0x01])
    if not success:
        return False, 0

    mil_active = False
    total_dtc_count = 0
    
    payloads = recv_isotp_messages(bus, range(0x7E8, 0x7F0), timeout=0.5)

    for ecu_id, payload in payloads.items():
        if len(payload) >= 3 and payload[0] == 0x41 and payload[1] == 0x01:
            # payload[2] contains monitor status:
            # Bit 7: MIL status (1 = active, 0 = inactive)
            # Bits 6-0: Count of confirmed DTCs
            ecu_mil = bool(payload[2] & 0x80)
            ecu_dtc_count = payload[2] & 0x7F
            
            mil_active = mil_active or ecu_mil
            total_dtc_count += ecu_dtc_count

    return mil_active, total_dtc_count

def _read_dtcs_from_service(bus, service_id):
    """
    Helper to request DTC bytes for a service (0x03 for Confirmed, 0x07 for Pending)
    and parse them. Supports ISO-TP multi-frame for multiple responding ECUs (0x7E8–0x7EF).
    Returns a list of decoded DTC string codes.
    """
    if not bus:
        return []

    clear_buffer(bus)
    success = send_obd_request(bus, 0x7DF, [0x01, service_id])
    if not success:
        return []

    payloads = recv_isotp_messages(bus, range(0x7E8, 0x7F0), timeout=2.0)
    dtc_list = []
    expected_response_service = 0x40 + service_id

    for ecu_id, payload in payloads.items():
        if len(payload) >= 2 and payload[0] == expected_response_service:
            # Payload format for Service 03/07:
            # payload[0]: Service response (e.g., 0x43 or 0x47)
            # payload[1:]: DTC bytes (each DTC is 2 bytes)
            dtc_bytes = payload[1:]
            for i in range(0, len(dtc_bytes) - 1, 2):
                b1 = dtc_bytes[i]
                b2 = dtc_bytes[i+1]
                code = decode_dtc_bytes(b1, b2)
                if code and code != "P0000" and code not in dtc_list:
                    dtc_list.append(code)

    return dtc_list

def read_confirmed_dtcs(bus):
    """Queries Service 03 (Stored/Confirmed DTCs)."""
    return _read_dtcs_from_service(bus, 0x03)

def read_pending_dtcs(bus):
    """Queries Service 07 (Pending DTCs)."""
    return _read_dtcs_from_service(bus, 0x07)

def run_full_scan(bus):
    """
    Executes a complete diagnostic scan of MIL status, confirmed, and pending DTCs.
    Returns:
    {
        "mil_active": bool,
        "confirmed_dtcs": list[str],
        "pending_dtcs": list[str]
    }
    """
    if not bus:
        raise RuntimeError("CAN bus is down, cannot perform diagnostic scan.")

    try:
        mil_active, dtc_count = read_mil_status(bus)
        confirmed = read_confirmed_dtcs(bus)
        pending = read_pending_dtcs(bus)
        
        return {
            "mil_active": mil_active,
            "confirmed_dtcs": confirmed,
            "pending_dtcs": pending
        }
    except Exception as e:
        logger.error(f"OBD-II Scan error: {e}")
        return {
            "mil_active": False,
            "confirmed_dtcs": [],
            "pending_dtcs": []
        }
