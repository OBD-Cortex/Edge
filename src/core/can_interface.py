import time
import logging
from core.config import CAN_PADDING_BYTE

logger = logging.getLogger(__name__)

try:
    import can
    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False

def init_can_bus():
    """
    Initializes the SocketCAN bus interface 'can0' with hardware filters.
    Raises RuntimeError if initialization fails.
    Returns the bus instance.
    """
    if not CAN_AVAILABLE:
        raise RuntimeError("python-can driver package is missing.")

    try:
        # We only care about OBD-II ECU responses: 0x7E8 to 0x7EF.
        # This completely drops normal vehicle traffic at the OS/socket level!
        filters = [{"can_id": 0x7E8, "can_mask": 0x7F8, "extended": False}]
        bus = can.interface.Bus(channel='can0', bustype='socketcan', can_filters=filters)
        logger.info("[✓] CAN Bus initialized on channel 'can0' (Filters: 0x7E8-0x7EF).")
        return bus
    except Exception as e:
        raise RuntimeError(f"SocketCAN device 'can0' could not be initialized: {e}")

def clear_buffer(bus):
    """
    Clears any pending/stale frames from the SocketCAN receive buffer.
    """
    if not bus:
        return
    try:
        while True:
            # timeout=0.0 means non-blocking read
            msg = bus.recv(timeout=0.0)
            if msg is None:
                break
    except Exception as e:
        logger.error(f"[CAN Bus] Error clearing buffer: {e}")

def send_obd_request(bus, arb_id, data):
    """
    Sends a standard 8-byte CAN query frame.
    """
    if not bus:
        return False
    try:
        # ISO-TP padding dynamically read from .env configuration
        padded_data = list(data) + [CAN_PADDING_BYTE] * (8 - len(data))
        msg = can.Message(
            arbitration_id=arb_id,
            data=padded_data,
            is_extended_id=False
        )
        bus.send(msg)
        return True
    except Exception as e:
        logger.error(f"[CAN Bus] Failed to send request: {e}")
        return False

def recv_isotp_messages(bus, expected_ids, timeout=1.0):
    """
    Listens for ISO-TP responses on the bus from any of the expected_ids.
    Handles Flow Control and multi-frame assembly for each responding ECU.
    Returns a dict mapping arbitration_id -> payload_bytes.
    """
    if not bus:
        return {}

    ecu_payloads = {}
    ecu_expected_len = {}
    ecu_flow_control_sent = {}

    start_time = time.time()

    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                break

            remaining = timeout - elapsed

            msg = bus.recv(timeout=min(remaining, 0.1))
            if msg is None:
                continue

            ecu_id = msg.arbitration_id

            if expected_ids and ecu_id not in expected_ids:
                continue

            data = list(msg.data)

            if not data:
                continue

            logger.debug(
                f"RX {hex(ecu_id)} : "
                + " ".join(f"{b:02X}" for b in data)
            )

            pci_type = data[0] & 0xF0

            # ---------------------------
            # Single Frame (SF)
            # ---------------------------
            if pci_type == 0x00:

                payload_len = data[0] & 0x0F

                if payload_len > 0:

                    ecu_payloads[ecu_id] = bytearray(
                        data[1:1 + payload_len]
                    )

                    ecu_expected_len[ecu_id] = payload_len

            # ---------------------------
            # First Frame (FF)
            # ---------------------------
            elif pci_type == 0x10:

                if len(data) < 2:
                    continue

                total_len = ((data[0] & 0x0F) << 8) | data[1]

                ecu_payloads[ecu_id] = bytearray(data[2:])
                ecu_expected_len[ecu_id] = total_len

                if not ecu_flow_control_sent.get(ecu_id):

                    fc_id = ecu_id - 0x08

                    time.sleep(0.01)

                    send_obd_request(
                        bus,
                        fc_id,
                        [0x30, 0x00, 0x00]
                    )

                    ecu_flow_control_sent[ecu_id] = True

            # ---------------------------
            # Consecutive Frame (CF)
            # ---------------------------
            elif pci_type == 0x20:

                if ecu_id in ecu_payloads:

                    ecu_payloads[ecu_id].extend(data[1:])

            # Stop if all active ISO-TP messages are complete
            if ecu_expected_len:

                complete = True

                for eid in ecu_expected_len:

                    if len(ecu_payloads.get(eid, b"")) < ecu_expected_len[eid]:
                        complete = False
                        break

                if complete:
                    break

    except Exception as e:
        logger.error(f"[CAN Bus] Error receiving ISO-TP frames: {e}")

    final_payloads = {}

    for eid, payload in ecu_payloads.items():

        expected_len = ecu_expected_len.get(eid, len(payload))

        final_payloads[eid] = bytes(payload[:expected_len])

    return final_payloads

def shutdown_can_bus(bus):
    """
    Gracefully shuts down the SocketCAN interface.
    """
    if bus:
        try:
            bus.shutdown()
            logger.info("[✓] CAN Bus socket closed cleanly.")
            return True
        except Exception as e:
            logger.error(f"[CAN Bus] Error closing CAN bus: {e}")
    return False
