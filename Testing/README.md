# Testing & Validation

This directory contains testing scripts and validation procedures for the OBD-Cortex Edge Gateway.

## Manual Trigger Loopback Test

You can verify hardware connectivity without a vehicle using a loopback test.

### Step 1: Start the Listener

Ensure the service is running (it starts automatically), or run it manually:

```bash
# Inside ~/obd-cortex
./obd-venv/bin/python src/main.py
```

*Output:* `TEST: System ready. Waiting for manual trigger...`

### Step 2: Send the Trigger

Open a **new terminal window** and send the secret handshake packet:

```bash
cansend can0 123#DEADBEEF
```

### Step 3: Verify Success

Check the logs of the main program:

```bash
journalctl -u obd-cortex.service -f
```

*Expected Output:*

> `RECEIVED: ID=0x123 Data=DEADBEEF`
> `PASSED: Manual test confirmed!`
> `--- SYSTEM HEALTHY: GoodBye! ---`
