# Device Service

Device management service for Android (ADB), iOS (pymobiledevice3), and HarmonyOS (HDC) devices.

## Service Structure

```
services/device-svc/
├── app/
│   ├── services/
│   │   ├── adb_service.py      # Android device management
│   │   ├── ios_service.py      # iOS device management
│   │   ├── harmony_service.py  # HarmonyOS device management
│   │   └── device_service.py   # Unified device service
│   ├── routes/
│   │   └── devices.py          # API endpoints
│   └── models/
│       └── device.py           # Pydantic models
```

## Adding New Device Types

1. Create a new service file (e.g., `harmony_service.py`) following the pattern from `adb_service.py` or `ios_service.py`
2. Implement required methods:
   - `discover_devices()` - List connected devices
   - `get_device_info(device_id)` - Get detailed device information
   - Device-specific operations (install, screenshot, etc.)
3. Use async subprocess execution for CLI tools
4. Return consistent Device model data

## iOS Device Service

Uses pymobiledevice3 for usbmuxd communication with iOS devices.

### Key Points

- Device identification uses UDID (Unique Device Identifier)
- CLI invoked via `python3 -m pymobiledevice3` with `--json` flag
- Pairing may require user confirmation on device screen
- Screen resolution/size mapped from ProductType (lockdown doesn't expose display info)

### Common Commands

```bash
# List connected devices
python3 -m pymobiledevice3 usbmux list --json

# Get device info
python3 -m pymobiledevice3 lockdown info --udid <UDID> --json

# Pair device
python3 -m pymobiledevice3 usbmux pair --udid <UDID>
```

## Android Device Service

Uses ADB (Android Debug Bridge) for device communication.

### Key Points

- Device identification uses serial number
- ADB must be in PATH or configured via `ADB_PATH` setting
- Async subprocess execution pattern for all ADB commands

## HarmonyOS Device Service

Uses HDC (HarmonyOS Device Connector) for device communication.

### Key Points

- Device identification uses serial number (similar to Android)
- HDC must be in PATH or configured via `HDC_PATH` setting
- Async subprocess execution pattern for all HDC commands
- HAP files are HarmonyOS Ability Packages (equivalent to APK)
- App management uses `bm` (Bundle Manager) and `aa` (Ability Manager) tools

### Common Commands

```bash
# List connected devices
hdc list targets

# Get device info
hdc -t <serial> shell getprop ro.product.model

# Install HAP
hdc -t <serial> install /path/to/app.hap

# Start app
hdc -t <serial> shell aa start -a <ability> -b <bundle>

# Take screenshot
hdc -t <serial> shell snapshot_display -f /data/local/tmp/screenshot.png
```

### Device Info Properties

HarmonyOS uses `param get` or `getprop` for device properties:
- `const.display.resolution` - Screen resolution
- `const.display.density` - Screen density
- `ro.build.version.harmonyos` - HarmonyOS version
