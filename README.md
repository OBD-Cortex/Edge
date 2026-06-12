# OBD-Cortex: Edge Device Controller

The **Edge Device Controller** is a production Python daemon running on Raspberry Pi 4 hardware connected to a vehicle's OBD-II port via an MCP2515 CAN Bus HAT.

---

## Service Architecture

Two independent systemd units work together:

```
CanMonitor.service          (foundational -- starts first)
  |-- ExecStartPre: ip link set can0 up type can bitrate 500000
  |-- Polls all ECU-supported Mode 01 live PIDs every second
  |-- Writes JSON records to logs/vehicle_data.log (rotating, 10 MB x 5)
  |-- Streams columnar output to journald
  v
Edge.service                (depends on CanMonitor -- starts after)
  |-- Requires=CanMonitor.service
  |-- Full OBD-II diagnostic scan: DTCs + live PIDs + freeze frame
  |-- HMAC-signed batch telemetry upload to Edge-Service
  |-- Automatic re-provisioning on HTTP 403 (stale secret self-healing)
```

**CanMonitor.service owns the CAN bus.** If it stops, Edge.service stops automatically via `Requires=`. CanMonitor can run alone on a bare Pi with no cloud setup.

---

## Key Architectural Details

1. **CAN-Bus Telemetry Acquisition:** Interfaces directly with physical OBD-II hardware via the `python-can` library. Queries Mode 01 (live PIDs), Mode 02 (freeze frame), Mode 03 (confirmed DTCs), and Mode 07 (pending DTCs).
2. **Full Live PID Coverage:** Dynamically probes the ECU's supported PID bitmask (PIDs 0x00/0x20/0x40/0x60) and polls all available sensors: RPM, speed, coolant temp, intake temp, throttle, MAF, fuel trims, oil temp, ECU voltage, barometric pressure, and more.
3. **Local VIN Decode:** The 17-character VIN is decoded entirely offline via a built-in WMI lookup table (`src/core/vin_decoder.py`). Brand, model year, and region are resolved without any network call and are included in every telemetry document.
4. **Offline Resilience:** Uses a local SQLite caching layer. Telemetry snapshots are buffered on the SD card and automatically flushed once cloud connectivity is restored.
5. **Cryptographic Signatures:** Payloads are signed using a local symmetric HMAC key. The Edge-Service verifies signatures to prevent spoofing.
6. **Automatic Re-Provisioning:** If the server returns HTTP 403 (stale HMAC secret after a device token rotation), the daemon automatically clears stale keys and re-provisions in-process. The operator only needs to update `DEVICE_TOKEN` in `.env` and restart once.
7. **No Version Pins:** `requirements.txt` uses latest stable packages. Appropriate for production deployments on controlled hardware.

---

## Repository Structure

- `src/main.py`: Diagnostic daemon entry point.
- `src/vehicle_monitor.py`: Standalone live PID polling daemon (run by CanMonitor.service).
- `src/core/can_interface.py`: SocketCAN channel management, ISO-TP multi-frame assembly, flow control.
- `src/core/config.py`: Environment variable loader.
- `src/core/crypto.py`: HMAC key management, payload signing, filesystem permission enforcement.
- `src/core/telemetry_buffer.py`: SQLite-backed offline buffer and batch flush client.
- `src/core/vin_decoder.py`: Offline WMI lookup table and SAE J1979 year character decoder.
- `src/services/dtc_sanitizer.py`: DTC byte decoder and natural language summary builder.
- `src/services/obd_scanner.py`: Mode 01/02/03/07 scanner, PID decoder table, freeze frame reader.
- `src/services/provisioning.py`: Device provisioning handshake and key management.
- `systemd/CanMonitor.service`: Foundational CAN bus + live data service.
- `systemd/Edge.service`: Diagnostic and telemetry upload service.

---

## Deployment (Raspberry Pi)

### 1. Install dependencies

```bash
cd /home/pi/Edge
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env: set EDGE_SERVICE_URL and DEVICE_TOKEN
```

### 3. Install and enable services

```bash
sudo cp systemd/CanMonitor.service /etc/systemd/system/
sudo cp systemd/Edge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable CanMonitor.service Edge.service
sudo systemctl start CanMonitor.service
# Edge.service starts automatically once CanMonitor is active
```

### 4. Monitor logs

```bash
# Live PID stream
journalctl -u CanMonitor.service -f

# Diagnostic and cloud sync logs
journalctl -u Edge.service -f

# Structured JSON data file
tail -f /home/pi/Edge/logs/vehicle_data.log
```

### After rotating a device token

Update `DEVICE_TOKEN` in `.env`, then restart Edge.service:

```bash
sudo systemctl restart Edge.service
```

Re-provisioning is automatic on the first cloud flush.

---

## Local Development Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python src/main.py
```

> [!NOTE]
> When running locally without a physical CAN interface, the script gracefully logs ECU unreachable errors. Use the loopback test scripts in `Testing/` to validate the CAN protocol layer.

---

## Installation & Validation

- Refer to [INSTALL.md](file:///home/bodz/OBD-Cortex/Edge/INSTALL.md) for step-by-step physical deployment instructions.
- Refer to [Testing/README.md](file:///home/bodz/OBD-Cortex/Edge/Testing/README.md) for loopback mock CAN bus verification.
