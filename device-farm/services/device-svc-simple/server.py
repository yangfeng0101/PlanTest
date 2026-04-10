#!/usr/bin/env python3
"""
Simple Device Service - Connects to real ADB devices
No external dependencies required
"""

import http.server
import json
import subprocess
import re
import threading
import time
from urllib.parse import urlparse, parse_qs

PORT = 8000
ADB_PATH = "/opt/homebrew/bin/adb"

# Device model name mapping (codename -> friendly name)
MODEL_NAMES = {
    # Xiaomi/Redmi
    "M2012K11AC": "K40",
    "M2012K11C": "K40",
    "M2012K11GC": "K40 Pro",
    "M2102J2SC": "K40 游戏增强版",
    "M2007J3SC": "K30 Ultra",
    "M2006J10C": "K30 5G",
    "M1910F4G": "K20",
    "M1908C3JGH": "K20 Pro",
    "23013RK75C": "K60",
    "23078RKD5C": "K60 Pro",
    "23127RA0EC": "K70",
    "23113RKC6C": "K70 Pro",
    "23116PN5BC": "15 Pro",
    # Xiaomi Digital Series
    "2201122C": "Xiaomi 12",
    "2201123C": "Xiaomi 12 Pro",
    "23078PND5C": "Xiaomi 13",
    "2211133C": "Xiaomi 13 Pro",
    "23127PN0CC": "Xiaomi 14",
    "24031PN0DC": "Xiaomi 14 Pro",
    "M2101K9C": "Xiaomi 11",
    "M2011K2C": "Xiaomi 11 Pro",
    "M2102K1C": "Xiaomi 11 Ultra",
    # Other Xiaomi
    "M2007J17C": "Xiaomi 10",
    "M2011J18C": "Xiaomi 10S",
    "M2007J1SC": "Xiaomi 10 Pro",
    "M2008J1SC": "Xiaomi 10 Ultra",
    # Samsung
    "SM-S928B": "Galaxy S24 Ultra",
    "SM-S926B": "Galaxy S24+",
    "SM-S921B": "Galaxy S24",
    "SM-S918B": "Galaxy S23 Ultra",
    "SM-S916B": "Galaxy S23+",
    "SM-S911B": "Galaxy S23",
    "SM-S908B": "Galaxy S22 Ultra",
    "SM-S906B": "Galaxy S22+",
    "SM-S901B": "Galaxy S22",
    # OnePlus
    "CPH2581": "OnePlus 12",
    "CPH2449": "OnePlus 11",
    "LE2121": "OnePlus 10 Pro",
    "LE2113": "OnePlus 9 Pro",
    "LE2101": "OnePlus 9",
    # Google Pixel
    "GC3VE": "Pixel 8 Pro",
    "GFE4J": "Pixel 8",
    "GP4BC": "Pixel 7 Pro",
    "GVU6C": "Pixel 7",
    "GF5KQ": "Pixel 6 Pro",
    "G7S100": "Pixel 6",
    # OPPO
    "PFEM00": "Find X6 Pro",
    "PGBM10": "Find X5 Pro",
    # Vivo
    "V2231A": "X90 Pro+",
    "V2188A": "X90",
    # Realme
    "RE58B2L1": "GT5 Pro",
    "RE54ABL1": "GT3",
    # Huawei
    "ALN-AL00": "Mate 60 Pro",
    "BRA-AL00": "Mate 60",
    "TAH-AN00": "P60 Pro",
    "ANA-AL00": "P40 Pro",
}

# Global device cache
devices_cache = {}
last_scan_time = 0

def run_adb(*args):
    """Run ADB command and return output"""
    try:
        result = subprocess.run(
            [ADB_PATH] + list(args),
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"ADB error: {e}")
        return ""

def get_device_info(device_id):
    """Get detailed device info"""
    info = {"id": device_id, "status": "online"}

    # Model
    model = run_adb("-s", device_id, "shell", "getprop", "ro.product.model")
    info["model"] = model or "Unknown"

    # Brand
    brand = run_adb("-s", device_id, "shell", "getprop", "ro.product.brand")
    info["brand"] = brand or "Unknown"
    info["brand"] = info["brand"].capitalize() if info["brand"] else "Unknown"

    # Name - use friendly name from mapping, or brand + model
    friendly_name = MODEL_NAMES.get(info["model"])
    if friendly_name:
        info["name"] = f"{info['brand']} {friendly_name}"
    else:
        info["name"] = f"{info['brand']} {info['model']}"

    # OS
    os_version = run_adb("-s", device_id, "shell", "getprop", "ro.build.version.release")
    info["os"] = "Android"
    info["osVersion"] = os_version or "Unknown"

    # Resolution
    resolution = run_adb("-s", device_id, "shell", "wm", "size")
    match = re.search(r'(\d+x\d+)', resolution)
    info["screenResolution"] = match.group(1) if match else "Unknown"

    # CPU
    cpu = run_adb("-s", device_id, "shell", "getprop", "ro.product.cpu.abi")
    info["cpu"] = cpu or "Unknown"

    # Memory
    meminfo = run_adb("-s", device_id, "shell", "cat", "/proc/meminfo")
    match = re.search(r'MemTotal:\s+(\d+)', meminfo)
    if match:
        total_mb = int(match.group(1)) // 1024
        info["memory"] = f"{total_mb}MB"
    else:
        info["memory"] = "Unknown"

    # Battery
    battery = run_adb("-s", device_id, "shell", "dumpsys", "battery")
    match = re.search(r'level:\s*(\d+)', battery)
    info["batteryLevel"] = int(match.group(1)) if match else 100

    info["screenSize"] = 6.0
    info["storage"] = "Unknown"
    info["tags"] = ["Android"]
    info["lastActiveAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
    info["occupiedBy"] = None
    info["occupiedAt"] = None

    return info

def scan_devices():
    """Scan connected devices"""
    global devices_cache, last_scan_time

    # Only scan every 5 seconds
    if time.time() - last_scan_time < 5:
        return list(devices_cache.values())

    last_scan_time = time.time()

    output = run_adb("devices", "-l")
    lines = output.split('\n')

    current_ids = set()
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            device_id = parts[0]
            status = parts[1]

            if status == "device":
                current_ids.add(device_id)
                if device_id not in devices_cache:
                    # New device - get info
                    print(f"Found new device: {device_id}")
                    info = get_device_info(device_id)
                    devices_cache[device_id] = info
                else:
                    # Update timestamp and status (device reconnected)
                    devices_cache[device_id]["lastActiveAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    devices_cache[device_id]["status"] = "online"

    # Mark offline devices
    for device_id in list(devices_cache.keys()):
        if device_id not in current_ids:
            devices_cache[device_id]["status"] = "offline"

    return list(devices_cache.values())

def get_device(device_id):
    """Get single device"""
    scan_devices()
    return devices_cache.get(device_id)

def occupy_device(device_id):
    """Occupy device"""
    if device_id in devices_cache:
        devices_cache[device_id]["status"] = "busy"
        devices_cache[device_id]["occupiedBy"] = "user-001"
        devices_cache[device_id]["occupiedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return devices_cache[device_id]
    return None

def release_device(device_id):
    """Release device"""
    if device_id in devices_cache:
        devices_cache[device_id]["status"] = "online"
        devices_cache[device_id]["occupiedBy"] = None
        devices_cache[device_id]["occupiedAt"] = None
        return devices_cache[device_id]
    return None

class DeviceHandler(http.server.BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_json({})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/health':
            self.send_json({"status": "ok", "service": "device-svc"})

        elif path == '/api/v1/devices':
            devices = scan_devices()
            self.send_json({"data": devices, "total": len(devices)})

        elif path.startswith('/api/v1/devices/'):
            parts = path.split('/')
            if len(parts) >= 4:
                device_id = parts[4]

                if device_id == 'stats':
                    devices = scan_devices()
                    stats = {
                        "total": len(devices),
                        "online": sum(1 for d in devices if d.get("status") == "online"),
                        "offline": sum(1 for d in devices if d.get("status") == "offline"),
                        "busy": sum(1 for d in devices if d.get("status") == "busy"),
                    }
                    self.send_json(stats)
                else:
                    device = get_device(device_id)
                    if device:
                        self.send_json(device)
                    else:
                        self.send_json({"error": "Device not found"}, 404)
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.endswith('/occupy'):
            device_id = path.split('/')[4]
            device = occupy_device(device_id)
            if device:
                self.send_json({"message": "Device occupied", "device": device})
            else:
                self.send_json({"error": "Device not found"}, 404)

        elif path.endswith('/release'):
            device_id = path.split('/')[4]
            device = release_device(device_id)
            if device:
                self.send_json({"message": "Device released", "device": device})
            else:
                self.send_json({"error": "Device not found"}, 404)

        else:
            self.send_json({"error": "Not found"}, 404)

if __name__ == '__main__':
    print(f"Starting Device Service on port {PORT}...")
    print(f"ADB path: {ADB_PATH}")

    # Initial scan
    print("Scanning for devices...")
    devices = scan_devices()
    print(f"Found {len(devices)} device(s)")
    for d in devices:
        print(f"  - {d['id']}: {d.get('name', 'Unknown')} ({d.get('model', 'Unknown')})")

    server = http.server.HTTPServer(('', PORT), DeviceHandler)
    print(f"\nServer running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
