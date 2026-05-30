import time
import random
from can_interface import send_obd_request, recv_obd_response, send_isotp_flow_control
from dtc_sanitizer import decode_dtc_bytes

# Global state to cycle through scenarios in simulation mode
_sim_index = 0

SIMULATION_SCENARIOS = [
    # Scenario 1: Healthy
    {"mil_active": False, "confirmed_dtcs": [], "pending_dtcs": []},
    # Scenario 2: Misfire
    {"mil_active": True, "confirmed_dtcs": ["P0300", "P0302"], "pending_dtcs": []},
    # Scenario 3: Lean Condition
    {"mil_active": True, "confirmed_dtcs": ["P0171"], "pending_dtcs": ["P0174"]},
    # Scenario 4: Overheating
    {"mil_active": True, "confirmed_dtcs": ["P0115", "P0116"], "pending_dtcs": []},
    # Scenario 5: Catalytic Converter
    {"mil_active": True, "confirmed_dtcs": ["P0420"], "pending_dtcs": ["P0430"]},
    # Scenario 6: EVAP Leak
    {"mil_active": True, "confirmed_dtcs": ["P0442"], "pending_dtcs": []},
    # Scenario 7: O2 Sensor
    {"mil_active": True, "confirmed_dtcs": ["P0130", "P0135"], "pending_dtcs": ["P0131"]},
    # Scenario 8: Multi-System Failure
    {"mil_active": True, "confirmed_dtcs": ["P0300", "P0420", "P0171", "P0507"], "pending_dtcs": ["P0128"]},
]

def read_vin(bus, is_simulated=False) -> str:
    """
    Queries the vehicle's ECU via standard OBD-II PID 09 02 over CAN frame 0x7DF.
    Supports ISO-TP multi-frame reassembly.
    Falls back to a default simulated VIN if the ECU is unresponsive or in simulation mode.
    """
    if is_simulated or not bus:
        return "VIN_12345_TEST"

    print("🔍 OBD-II: Querying ECU for vehicle VIN...")
    
    # Send request: Service 09 PID 02
    # Payload: [Len, Service, PID, 0, 0, 0, 0, 0]
    success = send_obd_request(bus, 0x7DF, [0x02, 0x09, 0x02])
    if not success:
        return "VIN_12345_TEST"

    try:
        vin_bytes = bytearray()
        flow_control_sent = False
        start_time = time.time()

        while time.time() - start_time < 3.0:
            msg = recv_obd_response(bus, 0x7E8, timeout=0.5)
            if not msg:
                continue

            data = msg.data
            pci = data[0] & 0xF0  # Protocol Control Information

            # Single Frame Response
            if pci == 0x00:
                length = data[0] & 0x0F
                # VIN is 17 bytes, so it will typically not fit in a single frame,
                # but we handle it just in case
                return data[3:3+length].decode('ascii', errors='ignore').strip()

            # First Frame (FF)
            elif pci == 0x10:
                length = ((data[0] & 0x0F) << 8) | data[1]
                # Store VIN bytes starting from index 4 (skip Len, Service, PID, Info)
                vin_bytes.extend(data[4:])
                
                if not flow_control_sent:
                    send_isotp_flow_control(bus, 0x7E0)
                    flow_control_sent = True

            # Consecutive Frame (CF)
            elif pci == 0x20:
                # Add data bytes starting from index 1 (skip CF sequence number byte)
                vin_bytes.extend(data[1:])
                
                # Standard VIN is 17 characters. Service response prefix takes 3 bytes
                if len(vin_bytes) >= 20:
                    decoded = vin_bytes[3:20].decode('ascii', errors='ignore').strip()
                    if len(decoded) == 17:
                        return decoded

        print("[!] OBD-II: VIN query timed out. ECU did not respond.")
    except Exception as e:
        print(f"[!] OBD-II: Error reading VIN: {e}")

    return "VIN_12345_TEST"

def read_mil_status(bus):
    """
    Queries Service 01 PID 01 to read MIL status (check engine light) and stored DTC count.
    Returns (mil_active: bool, dtc_count: int).
    """
    if not bus:
        return False, 0

    success = send_obd_request(bus, 0x7DF, [0x02, 0x01, 0x01])
    if not success:
        return False, 0

    msg = recv_obd_response(bus, 0x7E8, timeout=0.5)
    if msg and len(msg.data) >= 4 and msg.data[1] == 0x41 and msg.data[2] == 0x01:
        # msg.data[3] contains monitor status:
        # Bit 7: MIL status (1 = active, 0 = inactive)
        # Bits 6-0: Count of confirmed DTCs
        mil_active = bool(msg.data[3] & 0x80)
        dtc_count = msg.data[3] & 0x7F
        return mil_active, dtc_count

    return False, 0

def _read_dtcs_from_service(bus, service_id):
    """
    Helper to request DTC bytes for a service (0x03 for Confirmed, 0x07 for Pending)
    and parse them. Supports ISO-TP multi-frame.
    Returns a list of decoded DTC string codes.
    """
    if not bus:
        return []

    # Send Request
    # Service 03 or 07 request payload
    success = send_obd_request(bus, 0x7DF, [0x01, service_id])
    if not success:
        return []

    dtc_bytes = bytearray()
    flow_control_sent = False
    start_time = time.time()
    expected_response_service = 0x40 + service_id

    try:
        while time.time() - start_time < 2.0:
            msg = recv_obd_response(bus, 0x7E8, timeout=0.4)
            if not msg:
                continue

            data = msg.data
            pci = data[0] & 0xF0

            # Single Frame
            if pci == 0x00:
                length = data[0] & 0x0F
                # Data payload starts at index 1.
                # data[1] is the service response byte (e.g. 0x43 or 0x47)
                if length >= 2 and data[1] == expected_response_service:
                    dtc_bytes.extend(data[2:length+1])
                break

            # First Frame
            elif pci == 0x10:
                length = ((data[0] & 0x0F) << 8) | data[1]
                if data[2] == expected_response_service:
                    dtc_bytes.extend(data[3:]) # Store from index 3
                if not flow_control_sent:
                    send_isotp_flow_control(bus, 0x7E0)
                    flow_control_sent = True

            # Consecutive Frame
            elif pci == 0x20:
                dtc_bytes.extend(data[1:])
                # Stop if we read enough bytes based on first frame length indicator
                # (remember we skipped 3 bytes of header: PCI_High, PCI_Low, Service_Response)
                # But to be safe, standard OBD frames are short, we can collect up to the length.
                # Each DTC is 2 bytes. We can stop when we have enough data.
                pass

    except Exception as e:
        print(f"[!] OBD-II: Error reading DTCs for Service 0x{service_id:02X}: {e}")

    # Process dtc_bytes into pairs and decode
    dtc_list = []
    # Make sure we process in pairs
    for i in range(0, len(dtc_bytes) - 1, 2):
        b1 = dtc_bytes[i]
        b2 = dtc_bytes[i+1]
        code = decode_dtc_bytes(b1, b2)
        if code and code != "P0000":
            dtc_list.append(code)

    return dtc_list

def read_confirmed_dtcs(bus):
    """Queries Service 03 (Stored/Confirmed DTCs)."""
    return _read_dtcs_from_service(bus, 0x03)

def read_pending_dtcs(bus):
    """Queries Service 07 (Pending DTCs)."""
    return _read_dtcs_from_service(bus, 0x07)

def run_full_scan(bus, is_simulated=False):
    """
    Executes a complete diagnostic scan of MIL status, confirmed, and pending DTCs.
    Returns:
    {
        "mil_active": bool,
        "confirmed_dtcs": list[str],
        "pending_dtcs": list[str]
    }
    """
    if is_simulated or not bus:
        return simulate_scan()

    try:
        mil_active, dtc_count = read_mil_status(bus)
        confirmed = read_confirmed_dtcs(bus)
        pending = read_pending_dtcs(bus)
        
        # Cross-check: If MIL is active but we got no confirmed codes,
        # or if we got codes but MIL check didn't catch it, keep it aligned
        if confirmed and not mil_active:
            # Sometimes MIL takes a bit or represents a subset, but let's trust OBD readings
            pass

        return {
            "mil_active": mil_active,
            "confirmed_dtcs": confirmed,
            "pending_dtcs": pending
        }
    except Exception as e:
        print(f"[!] OBD-II Scan error: {e}")
        return {
            "mil_active": False,
            "confirmed_dtcs": [],
            "pending_dtcs": []
        }

def simulate_scan():
    """
    Simulates diagnostic scans. Cycles through the 8 scenarios on each call.
    """
    global _sim_index
    scenario = SIMULATION_SCENARIOS[_sim_index]
    
    # Increment simulation index for next call (wrap around)
    _sim_index = (_sim_index + 1) % len(SIMULATION_SCENARIOS)
    
    return {
        "mil_active": scenario["mil_active"],
        "confirmed_dtcs": list(scenario["confirmed_dtcs"]),
        "pending_dtcs": list(scenario["pending_dtcs"])
    }
