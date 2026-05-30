import time

try:
    import can
    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False

def init_can_bus():
    """
    Initializes the SocketCAN bus interface 'can0'.
    Raises RuntimeError if initialization fails.
    Returns the bus instance.
    """
    if not CAN_AVAILABLE:
        raise RuntimeError("python-can driver package is missing.")

    try:
        bus = can.interface.Bus(channel='can0', bustype='socketcan')
        print("[✓] CAN Bus initialized on channel 'can0'.")
        return bus
    except Exception as e:
        raise RuntimeError(f"SocketCAN device 'can0' could not be initialized: {e}")

def send_obd_request(bus, arb_id, data):
    """
    Sends a standard 8-byte CAN query frame.
    """
    if not bus:
        return False
    try:
        # Ensure data is padded to 8 bytes
        padded_data = list(data) + [0x00] * (8 - len(data))
        msg = can.Message(
            arbitration_id=arb_id,
            data=padded_data,
            is_extended_id=False
        )
        bus.send(msg)
        return True
    except Exception as e:
        print(f"[!] [CAN Bus] Failed to send request: {e}")
        return False

def recv_obd_response(bus, expected_id, timeout=0.5):
    """
    Blocks until a response with the expected arbitration ID is received or timeout expires.
    """
    if not bus:
        return None
    start_time = time.time()
    try:
        while time.time() - start_time < timeout:
            msg = bus.recv(timeout=timeout)
            if msg and msg.arbitration_id == expected_id:
                return msg
    except Exception as e:
        print(f"[!] [CAN Bus] Error receiving frame: {e}")
    return None

def send_isotp_flow_control(bus, flow_control_id=0x7E0):
    """
    Sends an ISO-TP Flow Control (FC) frame to the target ECU.
    Standard flow control parameters: [0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    (Flow Status: Clear to Send, Block Size: 0, Separation Time: 0)
    """
    return send_obd_request(bus, flow_control_id, [0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

def shutdown_can_bus(bus):
    """
    Gracefully shuts down the SocketCAN interface.
    """
    if bus:
        try:
            bus.shutdown()
            print("[✓] CAN Bus socket closed cleanly.")
            return True
        except Exception as e:
            print(f"[!] [CAN Bus] Error closing CAN bus: {e}")
    return False
