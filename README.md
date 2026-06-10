# OBD-Cortex: Edge Device Controller

The **Edge Device Controller** is a Python daemon designed to run persistently on Raspberry Pi hardware connected to a vehicle's OBD-II port. 

## Architecture Overview

1. **CAN-Bus Telemetry Acquisition**: Interfaces directly with physical OBD-II hardware via `python-can` to extract real-time vehicle telemetry and Diagnostic Trouble Codes (DTCs).
2. **Offline Resilience**: Features a highly robust local SQLite caching layer (`src/core/telemetry_buffer.py`). If the vehicle drives through a cellular dead zone, telemetry is buffered locally and automatically flushed to the cloud when connection restores.
3. **Cryptographic Assurance**: All payloads are signed using a local private key (`src/core/crypto.py`) before transmission to the `Edge_Service` API, preventing spoofing of vehicle data.
4. **Stripped-Down Logic**: Unlike legacy monolithic approaches, this edge client does NOT perform heavy DTC decodes or semantic NLP lookups. It strictly performs data acquisition and transmission, offloading processing to the cloud.

## Repository Structure

- `src/core/`: Offline buffering database, cryptographic keys, and CAN-bus interfacing logic.
- `src/services/`: Sanitization layers to prep OBD-II data for the cloud.
- `src/main.py`: The root daemon entrypoint.
- `systemd/`: Contains the `Edge.service` file for booting the daemon on Pi startup.

## Local Development (Quick Start)

While this daemon is designed for Raspberry Pi hardware connected to a physical vehicle, you can run it locally for testing:
1. Ensure **Python 3.10+** is installed.
2. Create and activate a virtual environment: `python -m venv venv && source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Copy the environment variables: `cp .env.example .env`
5. Run the daemon: `python src/main.py`

*(Note: The application will buffer telemetry into a local SQLite database if the `Edge_Service` API is unreachable. Without a physical or mocked virtual CAN interface, no actual vehicle data will be acquired).*

## Setup & Execution

Please refer to `INSTALL.md` for instructions on deploying this software onto Raspberry Pi hardware.
