# Testing & Validation Guide

This directory contains test scripts and validation guidelines for the OBD-Cortex Edge Gateway client.

---

## Hardware-Free Mock Loopback Test

You can verify the CAN Bus listening state, multi-frame reception, and telemetry generation logic without connecting to a physical vehicle's ECU. This uses a virtual SocketCAN loopback interface.

### Step 1: Initialize Virtual CAN Interface (Linux Host)

On a Linux machine or Raspberry Pi:
```bash
sudo ip link add dev can0 type vcan
sudo ip link set up can0
```

---

### Step 2: Start the Edge Daemon

Run the script in standard execution or manual trigger mode. In virtual mode, it logs ready states:

```bash
# Ensure virtualenv is active
source venv/bin/activate
python src/main.py
```

*Expected Output:*
`[✓] CAN Bus initialized on channel 'can0'.`
`OBD-II: Pinging vehicle ECU...`

---

### Step 3: Send a Mock CAN payload

Open a **separate terminal window** on the host. Send a mock OBD-II response payload (e.g. 0x7E8 response code frame):

```bash
# cansend syntax: cansend <interface> <can_id>#<hex_data>
# Sending service response 41 00 (positive ping response)
cansend can0 7E8#0341000000000000
```

---

### Step 4: Verify Logging Outputs

Inspect the terminal stdout logs or the systemd status to confirm the mock ping was successfully received, parsed, and logged:

```bash
# Check status if running via systemd
sudo journalctl -u Edge.service -f
```

*Expected Logs Confirmation:*
> `Vehicle ECU (0x7E8) responded to ping with payload: 4100000000000000`
> `VEHICLE VIN IDENTIFIED: [VIN]`
> `Triggering telemetry capture. Reason: State Changed`
> `Buffered 1 snapshot...`

