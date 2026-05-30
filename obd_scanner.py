import time
from can_interface import send_obd_request, recv_obd_response, send_isotp_flow_control
from dtc_sanitizer import decode_dtc_bytes

def ping_ecu(bus) -> bool:
    """
    Pings the vehicle's ECU using standard OBD-II Service 01 PID 00 (Supported PIDs).
    Returns True if the ECU responds, False if it times out/is unreachable.
    """
    if not bus:
        return False
    print("📡 OBD-II: Pinging vehicle ECU (Service 01 PID 00)...")
    success = send_obd_request(bus, 0x7DF, [0x02, 0x01, 0x00])
    if not success:
        return False
    msg = recv_obd_response(bus, 0x7E8, timeout=0.5)
    if msg and len(msg.data) >= 3 and msg.data[1] == 0x41 and msg.data[2] == 0x00:
        print("[✓] Vehicle ECU responded to ping.")
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
        print(f"🔍 OBD-II: Querying ECU for vehicle VIN (Attempt {attempt}/{max_attempts})...")
        success = send_obd_request(bus, 0x7DF, [0x02, 0x09, 0x02])
        if not success:
            if attempt < max_attempts:
                time.sleep(1.0)
            continue

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
                    vin_bytes.extend(data[1:])
                    
                    if len(vin_bytes) >= 20:
                        decoded = vin_bytes[3:20].decode('ascii', errors='ignore').strip()
                        if len(decoded) == 17:
                            return decoded

            print(f"[!] OBD-II: VIN query timed out on attempt {attempt}.")
        except Exception as e:
            print(f"[!] OBD-II: Error reading VIN on attempt {attempt}: {e}")
        
        if attempt < max_attempts:
            time.sleep(1.0)

    raise RuntimeError("Failed to retrieve vehicle VIN after retries.")

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
                if length >= 2 and data[1] == expected_response_service:
                    dtc_bytes.extend(data[2:length+1])
                break

            # First Frame
            elif pci == 0x10:
                length = ((data[0] & 0x0F) << 8) | data[1]
                if data[2] == expected_response_service:
                    dtc_bytes.extend(data[3:])
                if not flow_control_sent:
                    send_isotp_flow_control(bus, 0x7E0)
                    flow_control_sent = True

            # Consecutive Frame
            elif pci == 0x20:
                dtc_bytes.extend(data[1:])
                pass

    except Exception as e:
        print(f"[!] OBD-II: Error reading DTCs for Service 0x{service_id:02X}: {e}")

    # Process dtc_bytes into pairs and decode
    dtc_list = []
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
        print(f"[!] OBD-II Scan error: {e}")
        return {
            "mil_active": False,
            "confirmed_dtcs": [],
            "pending_dtcs": []
        }
