# OBD-Cortex: Edge Device Controller

The **Edge Device Controller** is a lightweight Python daemon designed to run persistently on Raspberry Pi 4 hardware connected to a vehicle's OBD-II port. 

---

## Key Architectural Details

1.  **CAN-Bus Telemetry Acquisition:** Interfaces directly with physical OBD-II hardware via the `python-can` library to query and assemble real-time vehicle RPM, Speed, and Diagnostic Trouble Codes (DTCs).
2.  **Offline Resilience:** Uses a local SQLite caching layer (`src/core/telemetry_buffer.py`). If the vehicle drives through cellular dead zones, telemetry snapshots (up to 100 per batch) are safely buffered on the SD card and automatically flushed once connectivity to the gateway is restored.
3.  **Cryptographic Signatures:** Payloads are signed using a local symmetric device key (`src/core/crypto.py`) concatenated with a UTC ISO-8601 timestamp. The `Edge-Service` verifies signatures to prevent telemetry spoofing.
4.  **No Version Pins:** To ensure you always run the latest stable libraries in production, `requirements.txt` does not restrict package versions. They will resolve to the latest stable packages upon deployment.

---

## Repository Structure

*   `src/core/can_interface.py`: Handles SocketCAN bus channels, flow control, and multi-frame ISO-TP assembly.
*   `src/core/crypto.py`: Enforces filesystem safety (0o700/0o600) on cryptographic keys and signs outgoing payloads.
*   `src/core/telemetry_buffer.py`: Local SQLite cache and batch flush client.
*   `src/services/dtc_sanitizer.py`: Decodes hex trouble codes (SAE definitions) and compiles natural language summaries for the LLM.
*   `src/services/obd_scanner.py`: Controls scanner loop, ECU handshakes, and VIN queries.
*   `systemd/`: Daemon templates to configure auto-booting on system startup.

---

## Local Development Setup

To run and evaluate the Edge client daemon on your workstation:
1.  Verify **Python 3.10+** is installed.
2.  Initialize virtual environment:
    ```bash
    python -m venv venv && source venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Configure local environment variables:
    ```bash
    cp .env.example .env
    ```
5.  Start the script:
    ```bash
    python src/main.py
    ```

> [!NOTE]
> When running locally without SocketCAN filters or a physical vehicle connection, the script will simulate or gracefully log unreachable ECU errors.

---

## Installation & Validation

*   Refer to [INSTALL.md](file:///home/bodz/OBD-Cortex/Edge/INSTALL.md) for step-by-step physical deployment instructions.
*   Refer to [Testing/README.md](file:///home/bodz/OBD-Cortex/Edge/Testing/README.md) to perform loopback mock CAN bus verification.

