# Embedded-Automotive-Edge
# Embedded-Automotive-Edge
### The IoT Gateway for [OBD-Cortex]

![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%204-red?logo=raspberrypi)
![Protocol](https://img.shields.io/badge/Protocol-CAN%20Bus%20%2F%20OBDII-orange)
![Database](https://img.shields.io/badge/Database-MongoDB%20Atlas-green?logo=mongodb)

**Embedded-Automotive-Edge** is the hardware interface layer of the **OBD-Cortex** diagnostics platform. It runs on a Raspberry Pi 4 connected to a vehicle's OBD-II port, capturing real-time telemetry (RPM, Speed, Temperatures, DTCs) via the CAN Bus protocol and streaming it to the cloud for analysis by the **[Hybrid-Automotive-RAG](https://github.com/YOUR_USERNAME/Hybrid-Automotive-RAG)** AI system.

---

## 🛠️ Hardware Architecture

This system relies on specific embedded hardware to ensure stable logic compatibility and safe power delivery from the vehicle.

| Component | Specification | Role |
| :--- | :--- | :--- |
| **SBC** | Raspberry Pi 4 Model B | Central processing gateway. |
| **CAN Interface** | **MCP2515 (SPI)** | CAN Controller & Transceiver (Connected via SPI0). |
| **Logic Level** | Bi-Directional Converter | Safely bridges 5V (MCP2515) to 3.3V (Raspberry Pi). |
| **Connectivity** | ZTE MF79U USB Modem | Provides 4G/LTE internet for cloud uploads. |
| **Power** | DC-DC Buck Converter | Steps down 12V Car Battery to stable 5V/3A for Pi. |
| **Protection** | Glass Fuse (5A) + Switch | Overcurrent protection and manual isolation. |

---

## 🔌 Software Stack

* **OS:** Raspberry Pi OS (Bookworm/Bullseye)
* **Driver:** `mcp2515-can0` (SocketCAN overlay)
* **Language:** Python 3.13
* **Virtual Env:** `venv` (Isolated environment)
* **Libraries:** `python-can`, `python-dotenv`, `requests`

---

## 🚀 Installation & Setup

### 1. Hardware Configuration
Enable the SPI interface and load the MCP2515 driver overlay.

1.  Open the config file:
    ```bash
    sudo nano /boot/firmware/config.txt
    # (Or /boot/config.txt on older OS versions)
    ```

2.  Add the following lines to the bottom:
    ```ini
    dtparam=spi=on
    dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25
    ```
    *(Note: Ensure `oscillator` matches your crystal: 8000000 for 8MHz, 16000000 for 16MHz)*.

3.  Reboot the Pi:
    ```bash
    sudo reboot
    ```

### 2. Environment Setup
We use a Python Virtual Environment to manage dependencies safely.

```bash
# 1. Create Project Directory
mkdir -p ~/obd-cortex
cd ~/obd-cortex

# 2. Create Virtual Environment (Python 3.13)
python3 -m venv obd-venv

# 3. Activate Environment
source obd-venv/bin/activate  # (Or activate.fish for Fish shell)

# 4. Install Dependencies
pip install --upgrade pip
pip install python-can requests python-dotenv

```

### 3. Service Deployment (Auto-Start)

To run the logger automatically on boot, we use a systemd service.

1. Copy the service file to the system directory:
```bash
sudo cp obd-cortex.service /etc/systemd/system/

```


2. Enable and Start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable obd-cortex.service
sudo systemctl start obd-cortex.service

```


3. Check Status:
```bash
sudo systemctl status obd-cortex.service

```



## 📊 Telemetry Data Format

Telemetry captured from the CAN Bus is formatted into standard JSON payloads before buffering and syncing:

```json
{
  "vehicle_id": "17_CHAR_VIN_NUMBER",
  "timestamp": "2026-06-05T11:12:02.628000+00:00",
  "mil_active": false,
  "dtc_count": 0,
  "confirmed_dtcs": [],
  "pending_dtcs": [],
  "system_status": "healthy",
  "scan_summary": "System healthy. CHECK ENGINE OFF. No confirmed or pending Diagnostic Trouble Codes (DTCs) detected."
}
```

---

*(Note: Testing and Validation instructions have been moved to the `Testing/` directory. Please see `Testing/README.md` for details.)*

