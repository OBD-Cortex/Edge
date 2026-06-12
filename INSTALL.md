# Edge Device Setup Guide

This guide outlines how to deploy the OBD-Cortex Edge daemon onto a Raspberry Pi running Linux (e.g., Raspberry Pi OS / Debian).

---

## System Requirements
- Raspberry Pi (3B, 4, or Zero 2 W recommended)
- A connected CAN-Bus hat (e.g., PiCAN2 or similar MCP2515-based hardware)
- Python 3.10+
- `can-utils` package (for mock testing and utilities)

---

## Database Caching Setup

This application utilizes a local SQLite database file (`telemetry_buffer.db`) to cache telemetry in real-time if the cell network goes down. 
*   **Zero manual database configuration is required.**
*   The SQLite buffer initialization is fully automated and runs inside `src/core/telemetry_buffer.py`. The schema structure is created automatically on start.

---

## Private Key Permissions & provisioning

To enable cryptographic signature generation:
1.  During provisioning, a device secret token is saved in a `.keys/` directory under the project root.
2.  **Permissions Warning:** The daemon strictly checks file system permissions on startup. The `.keys/` folder must be restricted to mode `0o700` (read/write/execute by owner only) and the secret key file to `0o600` (read/write by owner only). If permissions are too open, the daemon will log warnings and force the change automatically.

---

## Environment Configuration

Create a `.env` file in the root directory:

```env
# The endpoint for your central Edge-Service gateway
EDGE_SERVICE_URL=https://edge.yourdomain.com

# Device token generated via the Admin Dashboard
DEVICE_TOKEN=YOUR_HEX_DEVICE_TOKEN_HERE

# Diagnostics loop configuration
SCAN_INTERVAL=60.0
HEARTBEAT_INTERVAL=1800.0
```

---

## Service Installation

Perform the following commands on the Raspberry Pi:

```bash
# 1. Update system package repository
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip can-utils

# 2. Setup project path & virtual environment
cd /home/pi/OBD-Cortex/Edge
python3 -m venv venv
source venv/bin/activate

# 3. Install latest stable dependencies
pip install -r requirements.txt
```

---

## Running persistently as a systemd Daemon

To ensure the telemetry acquisition starts automatically whenever the vehicle turns on:

1.  Inspect and modify the paths in `systemd/Edge.service` to match your Raspberry Pi user name and install directory.
2.  Copy the service configuration template to your system directory:
    ```bash
    sudo cp systemd/Edge.service /etc/systemd/system/
    ```
3.  Enable and start the daemon:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable Edge.service
    sudo systemctl start Edge.service
    ```
4.  Track logging output in real-time:
    ```bash
    sudo journalctl -u Edge.service -f
    ```

