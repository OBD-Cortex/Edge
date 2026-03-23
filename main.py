#!/usr/bin/env python3
import os
import time
import can
import isotp
import logging

# ==============================
# CONFIG
# ==============================
REQUEST_ID = 0x7D0
RESPONSE_ID = 0x7D8 # if its not response try 0x7D9 or 0x7DA

# Example requests
OBD_RPM = bytes([0x01, 0x0C])
OBD_VIN = bytes([0x09, 0x02])
OBD_DTC = bytes([0x03])

# ==============================
# LOGGING
# ==============================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [OBD-CORTEX] - %(levelname)s - %(message)s'
)

# ==============================
# SETUP CAN
# ==============================
def setup_can_interface():
    logging.info("CONFIG: Initializing MCP2515 hardware...")

    os.system("sudo ip link set can0 down")
    time.sleep(1)

    exit_code = os.system(
        "sudo ip link set can0 up type can bitrate 500000"
    )

    if exit_code == 0:
        logging.info("SUCCESS: can0 interface is UP.")
        return True
    else:
        logging.error("FAILURE: Could not setup can0.")
        return False


# ==============================
# CREATE ISO-TP STACK
# ==============================
def create_isotp_stack(bus):
    addr = isotp.Address(
        isotp.AddressingMode.Normal_11bits,
        txid=REQUEST_ID,
        rxid=RESPONSE_ID
    )

    stack = isotp.CanStack(
        bus=bus,
        address=addr,
        params={
            'stmin': 0,
            'blocksize': 8,
            'wftmax': 0,
            'll_data_length': 8,
            'tx_padding': 0x00
        }
    )

    return stack


# ==============================
# SEND + RECEIVE ISO-TP
# ==============================
def send_and_receive(stack, request, timeout=2):
    logging.info(f"SENT (ISO-TP): {request.hex().upper()}")

    stack.send(request)

    start_time = time.time()

    while time.time() - start_time < timeout:
        stack.process()  # 🔥 VERY IMPORTANT

        if stack.available():
            response = stack.recv()
            logging.info(f"RECEIVED (ISO-TP): {response.hex().upper()}")
            return response

        time.sleep(0.01)

    logging.warning("No response received")
    return None


# ==============================
# DECODERS
# ==============================
def decode_rpm(data):
    if len(data) >= 4:
        A = data[2]
        B = data[3]
        return ((A * 256) + B) / 4
    return None


def decode_vin(data):
    try:
        vin = ''.join(chr(b) for b in data[3:])
        return vin
    except:
        return None


def decode_dtc(data):
    dtcs = []
    for i in range(1, len(data), 2):
        if i+1 >= len(data):
            break

        b1 = data[i]
        b2 = data[i+1]

        if b1 == 0 and b2 == 0:
            continue

        first = ['P', 'C', 'B', 'U'][b1 >> 6]
        code = f"{first}{(b1>>4)&3}{b1&0xF}{b2>>4}{b2&0xF}"
        dtcs.append(code)

    return dtcs


# ==============================
# MAIN LOOP
# ==============================
def run_obd():
    logging.info("OBD: Starting ISO-TP communication...")

    try:
        with can.interface.Bus(channel='can0', interface='socketcan') as bus:

            stack = create_isotp_stack(bus)

            while True:
                # 🔹 RPM
                resp = send_and_receive(stack, OBD_RPM)
                if resp:
                    rpm = decode_rpm(resp)
                    if rpm:
                        logging.info(f"DECODED: RPM = {rpm}")

                # 🔹 VIN (multi-frame example)
                resp = send_and_receive(stack, OBD_VIN)
                if resp:
                    vin = decode_vin(resp)
                    if vin:
                        logging.info(f"DECODED: VIN = {vin}")

                # 🔹 DTCs
                resp = send_and_receive(stack, OBD_DTC)
                if resp:
                    dtcs = decode_dtc(resp)
                    if dtcs:
                        logging.info(f"DECODED: DTCs = {dtcs}")

                time.sleep(3)

    except Exception as e:
        logging.error(f"ERROR: {e}")


# ==============================
# MAIN
# ==============================
def main():
    if not setup_can_interface():
        return

    run_obd()


if __name__ == "__main__":
    main()
