# Edge Device Setup Guide

This guide outlines how to deploy the OBD-Cortex Edge daemon onto a Raspberry Pi running Linux (e.g., Raspberry Pi OS).

## System Requirements
- Raspberry Pi (3B, 4, or Zero 2 W recommended)
- A connected CAN-Bus hat (e.g., PiCAN2 or similar MCP2515-based hardware)
- Python 3.10+

## Database Scripts

This application utilizes a local SQLite database to buffer telemetry during cellular dead zones. You do not need to manually run any SQL scripts; the schema initialization logic is fully automated and documented within `src/core/telemetry_buffer.py`. The `init_buffer()` function creates the necessary `telemetry_cache` table upon startup.

## Environment Variables

Create a `.env` file in the root directory:

```env
# The endpoint for your Edge_Service droplet
EDGE_API_URL=https://edge.yourdomain.com/ingest

# Device identifier generated during provisioning
DEVICE_ID=pi_node_xyz123

# The private cryptographic key for signing payloads
PRIVATE_KEY_PATH=/etc/obd-cortex/keys/private.pem
```

## Installation

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip can-utils

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running as a Daemon

To ensure the Edge logger starts automatically whenever the vehicle turns on (booting the Raspberry Pi), install the systemd service:

1. Edit the paths in `systemd/Edge.service` to match your Raspberry Pi user (typically `pi` or a custom username).
2. Copy the service file to the systemd directory:
   ```bash
   sudo cp systemd/Edge.service /etc/systemd/system/
   ```
3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable Edge.service
   sudo systemctl start Edge.service
   ```
4. View real-time logs:
   ```bash
   sudo journalctl -u Edge.service -f
   ```
