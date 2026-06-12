import time
import logging
from core.can_interface import send_obd_request, clear_buffer, recv_isotp_messages
from services.dtc_sanitizer import decode_dtc_bytes

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mode 01 PID decoder table.
# Each entry: pid -> (name, unit, decode_fn)
# decode_fn receives the raw payload bytes (after the service/PID header)
# and returns a scaled numeric value.
# ---------------------------------------------------------------------------
def _decode_engine_load(b):    return round((b[0] / 255.0) * 100.0, 1)
def _decode_temp(b):           return b[0] - 40
def _decode_fuel_trim(b):      return round((b[0] / 128.0 - 1.0) * 100.0, 1)
def _decode_fuel_pressure(b):  return b[0] * 3
def _decode_map(b):            return b[0]  # kPa absolute
def _decode_rpm(b):            return round(((b[0] * 256) + b[1]) / 4.0, 1)
def _decode_speed(b):          return b[0]  # km/h
def _decode_timing(b):         return (b[0] / 2.0) - 64.0
def _decode_maf(b):            return round(((b[0] * 256) + b[1]) / 100.0, 2)  # g/s
def _decode_throttle(b):       return round((b[0] / 255.0) * 100.0, 1)
def _decode_runtime(b):        return (b[0] * 256) + b[1]  # seconds
def _decode_mil_distance(b):   return (b[0] * 256) + b[1]  # km
def _decode_fuel_level(b):     return round((b[0] / 255.0) * 100.0, 1)
def _decode_baro(b):           return b[0]  # kPa
def _decode_fuel_rail_kpa(b):  return round(((b[0] * 256) + b[1]) * 0.079, 2)  # kPa
def _decode_fuel_rail_mpa(b):  return round(((b[0] * 256) + b[1]) * 0.1, 2)   # kPa
def _decode_evap_pressure(b):  return round(((b[0] * 256) + b[1]) / 4.0, 2)   # Pa

PID_DECODERS = {
    0x04: ("engine_load_pct",       "%",     _decode_engine_load,  1),
    0x05: ("coolant_temp_c",        "degC",  _decode_temp,         1),
    0x06: ("stft_b1_pct",           "%",     _decode_fuel_trim,    1),
    0x07: ("ltft_b1_pct",           "%",     _decode_fuel_trim,    1),
    0x08: ("stft_b2_pct",           "%",     _decode_fuel_trim,    1),
    0x09: ("ltft_b2_pct",           "%",     _decode_fuel_trim,    1),
    0x0A: ("fuel_pressure_kpa",     "kPa",   _decode_fuel_pressure,1),
    0x0B: ("intake_map_kpa",        "kPa",   _decode_map,          1),
    0x0C: ("engine_rpm",            "rpm",   _decode_rpm,          2),
    0x0D: ("vehicle_speed_kmh",     "km/h",  _decode_speed,        1),
    0x0E: ("timing_advance_deg",    "deg",   _decode_timing,       1),
    0x0F: ("intake_air_temp_c",     "degC",  _decode_temp,         1),
    0x10: ("maf_rate_gs",           "g/s",   _decode_maf,          2),
    0x11: ("throttle_pos_pct",      "%",     _decode_throttle,     1),
    0x1F: ("engine_run_time_s",     "s",     _decode_runtime,      2),
    0x21: ("mil_distance_km",       "km",    _decode_mil_distance, 2),
    0x2F: ("fuel_level_pct",        "%",     _decode_fuel_level,   1),
    0x33: ("baro_pressure_kpa",     "kPa",   _decode_baro,         1),
    0x3C: ("cat_temp_b1s1_c",       "degC",  lambda b: round(((b[0]*256+b[1])/10.0)-40, 1), 2),
    0x3E: ("cat_temp_b2s1_c",       "degC",  lambda b: round(((b[0]*256+b[1])/10.0)-40, 1), 2),
    0x42: ("ecu_voltage_v",         "V",     lambda b: round((b[0]*256+b[1])/1000.0, 3), 2),
    0x43: ("abs_load_pct",          "%",     lambda b: round((b[0]*256+b[1])/2.55, 1),   2),
    0x45: ("rel_throttle_pct",      "%",     _decode_throttle,     1),
    0x46: ("ambient_air_temp_c",    "degC",  _decode_temp,         1),
    0x47: ("abs_throttle_b_pct",    "%",     _decode_throttle,     1),
    0x49: ("abs_throttle_c_pct",    "%",     _decode_throttle,     1),
    0x4A: ("acc_pedal_d_pct",       "%",     _decode_throttle,     1),
    0x4B: ("acc_pedal_e_pct",       "%",     _decode_throttle,     1),
    0x4C: ("commanded_throttle_pct","%",     _decode_throttle,     1),
    0x4D: ("mil_run_time_min",      "min",   _decode_runtime,      2),
    0x4E: ("clr_distance_km",       "km",    _decode_mil_distance, 2),
    0x5C: ("engine_oil_temp_c",     "degC",  _decode_temp,         1),
    0x5E: ("fuel_rate_lh",          "L/h",   lambda b: round((b[0]*256+b[1])/20.0, 2), 2),
}


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
        # Any valid ISO-TP payload confirms the ECU is alive.
        # Positive response starts with 0x41; Negative with 0x7F.
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
                    # ISO-TP assembled payload:
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
    Aggregates checks and counts across all responding ECUs (0x7E8-0x7EF).
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
    and parse them. Supports ISO-TP multi-frame for multiple responding ECUs (0x7E8-0x7EF).
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


def read_supported_pids(bus) -> set:
    """
    Queries Service 01 PID availability bitmasks (0x00, 0x20, 0x40, 0x60).
    Each bitmask PID returns a 4-byte bitmap of supported PIDs in that range.
    Returns a set of supported PID integers (from PID_DECODERS keys only).
    """
    if not bus:
        return set()

    # Availability PIDs: 0x00 covers 0x01-0x1F, 0x20 covers 0x21-0x3F, etc.
    availability_pids = [0x00, 0x20, 0x40, 0x60]
    supported = set()

    for avail_pid in availability_pids:
        clear_buffer(bus)
        if not send_obd_request(bus, 0x7DF, [0x02, 0x01, avail_pid]):
            continue

        payloads = recv_isotp_messages(bus, range(0x7E8, 0x7F0), timeout=0.5)

        for ecu_id, payload in payloads.items():
            if len(payload) >= 6 and payload[0] == 0x41 and payload[1] == avail_pid:
                # 4 bytes of bitmask: payload[2..5]
                # Bit 31 of first byte = PID avail_pid+1, bit 0 of last byte = avail_pid+32
                bitmask = (payload[2] << 24) | (payload[3] << 16) | (payload[4] << 8) | payload[5]
                for bit_pos in range(32):
                    if bitmask & (0x80000000 >> bit_pos):
                        pid = avail_pid + bit_pos + 1
                        # Only track PIDs we have a decoder for
                        if pid in PID_DECODERS:
                            supported.add(pid)

        # If this avail_pid itself is not supported, no point querying higher ranges
        # (indicated by the last bit of the bitmask -- bit 0 means 'next group supported')
        # However, some ECUs lie, so we query all groups regardless.

    logger.info(f"OBD-II: Supported PIDs found: {sorted(supported)}")
    return supported


def _read_single_pid(bus, pid: int):
    """
    Reads a single Mode 01 PID and returns the decoded scaled value.
    Returns None on failure or unsupported PID.
    """
    if pid not in PID_DECODERS:
        return None

    name, unit, decode_fn, min_bytes = PID_DECODERS[pid]

    clear_buffer(bus)
    if not send_obd_request(bus, 0x7DF, [0x02, 0x01, pid]):
        return None

    payloads = recv_isotp_messages(bus, range(0x7E8, 0x7F0), timeout=0.4)

    for ecu_id, payload in payloads.items():
        if len(payload) >= 2 + min_bytes and payload[0] == 0x41 and payload[1] == pid:
            try:
                return decode_fn(payload[2:])
            except Exception as e:
                logger.debug(f"OBD-II: PID 0x{pid:02X} decode error: {e}")

    return None


def read_live_pids(bus, supported_pids: set) -> dict:
    """
    Polls all PIDs present in both supported_pids and PID_DECODERS.
    Returns a dict of {name: value} for all successfully read PIDs.
    Skips PIDs that return None (unsupported or bus timeout).
    """
    if not bus:
        return {}

    results = {}
    for pid in sorted(supported_pids):
        if pid not in PID_DECODERS:
            continue
        name, unit, _, _ = PID_DECODERS[pid]
        value = _read_single_pid(bus, pid)
        if value is not None:
            results[name] = {"value": value, "unit": unit}

    return results


def read_freeze_frame(bus) -> dict:
    """
    Queries Service 02 (Freeze Frame) for the snapshot captured when a DTC was set.
    Reads the same live PIDs but from freeze frame memory.
    Returns a dict of decoded values, or empty dict if no freeze frame is stored.
    """
    if not bus:
        return {}

    # Service 02 PID 0x02 with Frame Number 0x00 returns the freeze frame DTC
    clear_buffer(bus)
    if not send_obd_request(bus, 0x7DF, [0x03, 0x02, 0x02, 0x00]):
        return {}

    payloads = recv_isotp_messages(bus, range(0x7E8, 0x7F0), timeout=1.0)
    freeze_dtc = None
    for ecu_id, payload in payloads.items():
        if len(payload) >= 4 and payload[0] == 0x42 and payload[1] == 0x02:
            freeze_dtc = decode_dtc_bytes(payload[2], payload[3])
            break

    if not freeze_dtc:
        return {}

    # Read a core set of freeze frame PIDs (Service 02 requests)
    freeze_pids = [0x04, 0x05, 0x0B, 0x0C, 0x0D, 0x0F, 0x10, 0x11]
    frame_data = {"freeze_dtc": freeze_dtc}

    for pid in freeze_pids:
        if pid not in PID_DECODERS:
            continue
        name, unit, decode_fn, min_bytes = PID_DECODERS[pid]
        clear_buffer(bus)
        # Service 02 request: [length, 0x02, PID, frame_number]
        if not send_obd_request(bus, 0x7DF, [0x03, 0x02, pid, 0x00]):
            continue
        payloads = recv_isotp_messages(bus, range(0x7E8, 0x7F0), timeout=0.4)
        for ecu_id, payload in payloads.items():
            if len(payload) >= 2 + min_bytes and payload[0] == 0x42 and payload[1] == pid:
                try:
                    frame_data[name] = {"value": decode_fn(payload[2:]), "unit": unit}
                except Exception as e:
                    logger.debug(f"OBD-II: Freeze frame PID 0x{pid:02X} decode error: {e}")

    logger.info(f"OBD-II: Freeze frame read. Triggered by DTC: {freeze_dtc}")
    return frame_data


def run_full_scan(bus, supported_pids: set = None) -> dict:
    """
    Executes a complete diagnostic scan:
      - MIL status and DTC count
      - Confirmed DTCs (Service 03)
      - Pending DTCs (Service 07)
      - Live sensor PIDs (Service 01, all supported)
      - Freeze frame (Service 02, if DTCs are present)

    Returns:
    {
        "mil_active": bool,
        "confirmed_dtcs": list[str],
        "pending_dtcs": list[str],
        "live_pids": dict,
        "freeze_frame": dict
    }
    """
    if not bus:
        raise RuntimeError("CAN bus is down, cannot perform diagnostic scan.")

    empty = {
        "mil_active": False,
        "confirmed_dtcs": [],
        "pending_dtcs": [],
        "live_pids": {},
        "freeze_frame": {},
    }

    try:
        mil_active, dtc_count = read_mil_status(bus)
        confirmed = read_confirmed_dtcs(bus)
        pending = read_pending_dtcs(bus)

        # Probe supported PIDs on first call if not passed in
        if supported_pids is None:
            supported_pids = read_supported_pids(bus)

        live = read_live_pids(bus, supported_pids)

        # Only read freeze frame if there are confirmed DTCs, to avoid unnecessary traffic
        freeze = {}
        if confirmed:
            freeze = read_freeze_frame(bus)

        return {
            "mil_active": mil_active,
            "confirmed_dtcs": confirmed,
            "pending_dtcs": pending,
            "live_pids": live,
            "freeze_frame": freeze,
        }
    except Exception as e:
        logger.error(f"OBD-II Scan error: {e}")
        return empty
