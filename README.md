# Embedded-Automotive-Edge
### The IoT Gateway for [OBD-Cortex]

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%204-red?logo=raspberrypi)
![Protocol](https://img.shields.io/badge/Protocol-CAN%20Bus%20%2F%20OBDII-orange)
![Database](https://img.shields.io/badge/Database-MongoDB%20Atlas-green?logo=mongodb)

**Embedded-Automotive-Edge** is the hardware interface layer of the **OBD-Cortex** diagnostics platform. It runs on a Raspberry Pi 4 connected to a vehicle's OBD-II port, capturing real-time telemetry (RPM, Speed, Temperatures, DTCs) via the CAN Bus protocol and streaming it to the cloud for analysis by the **[Hybrid-Automotive-RAG](https://github.com/YOUR_USERNAME/Hybrid-Automotive-RAG)** AI system.

---

## 🛠️ Hardware Architecture

This system is designed to run on specific embedded hardware to ensure stable 3.3V logic compatibility and reliable connectivity.

| Component | Specification | Role |
| :--- | :--- | :--- |
| **SBC** | Raspberry Pi 4 Model B | Central processing gateway. |
| **CAN Interface** | **RS485 CAN HAT** (or SN65HVD230) | Converts CAN High/Low signals to SPI for the Pi. |
| **Connectivity** | ZTE MF79U USB Modem | Provides 4G/LTE internet for cloud uploads. |
| **Power** | 5.1V 3.0A Power Bank | Dedicated power supply to prevent voltage drops. |
| **Cabling** | OBD-II to DB9 | Physical connection to the vehicle's diagnostic port. |

---

## 🔌 Software Stack

* **OS:** Raspberry Pi OS / Yocto (Embedded Linux)
* **Driver:** SocketCAN (Native Linux CAN support)
* **Language:** Python 3.10+
* **Libraries:** `python-can`, `pymongo`, `python-dotenv`
* **Cloud:** MongoDB Atlas (TimeSeries Collection)

---

## 🚀 Installation & Setup

### 1. Prerequisites
Ensure your Raspberry Pi has the CAN HAT drivers installed and the interface is up.
```bash
# Edit /boot/config.txt to enable SPI and CAN
sudo nano /boot/config.txt
# Add: dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25

```
