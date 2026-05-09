# Device Service

Device management service for Android-compatible devices via ADB and optional iOS devices via a Mac host-side iOS Agent.

## Features

- Device discovery and monitoring
- Device status tracking
- Device occupation/release
- Screenshot capture
- Shell command execution
- Real-time WebSocket updates
- Runtime device capability model for display OS, connection type, drivers, and supported features

## Device Capability Model

Device responses keep legacy `os/os_version` fields, and also include runtime fields:

- `display_os` / `display_os_version` for user-facing platform display
- `connection_type` for the active connection, such as `adb`
- `drivers` for metrics, screen, UI hierarchy, control, and automation backends
- `capabilities` for feature availability

HarmonyOS phones connected through ADB are treated as Android-compatible devices: they display as HarmonyOS, while metrics, scrcpy screen streaming, remote control, screenshots, and UIAutomator hierarchy still use the ADB-compatible drivers.

iOS devices discovered through `IOS_AGENT_URL` expose script automation and static screenshot/UI hierarchy debug when the Agent reports Appium/XCUITest ready. Screen mirroring and remote control remain disabled for iOS until the dedicated realtime WDA screen session path is implemented.

## Prerequisites

- Python 3.11+
- Android SDK Platform Tools (ADB)

## Installation

```bash
pip install -r requirements.txt
```

## Running

```bash
cd src
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## API Endpoints

### REST API

- `GET /api/v1/devices` - List all devices
- `GET /api/v1/devices/stats` - Device statistics
- `GET /api/v1/devices/scan` - Trigger device scan
- `GET /api/v1/devices/:id` - Get device details
- `PATCH /api/v1/devices/:id` - Update device info
- `POST /api/v1/devices/:id/occupy` - Occupy device
- `POST /api/v1/devices/:id/release` - Release device
- `GET /api/v1/devices/:id/screenshot` - Get screenshot
- `POST /api/v1/devices/:id/command` - Execute shell command
- `GET /api/v1/devices/:id/logs` - Get device logs

### WebSocket

- `WS /api/v1/devices/ws` - Real-time device updates

## Environment Variables

- `SERVICE_NAME` - Service name (default: device-svc)
- `SERVICE_VERSION` - Service version (default: 1.0.0)
- `PORT` - Server port (default: 8001)
- `DEBUG` - Debug mode (default: true)
- `DATABASE_URL` - PostgreSQL connection URL
- `REDIS_URL` - Redis connection URL
- `ADB_PATH` - Path to ADB executable
- `IOS_AGENT_URL` - Optional Mac iOS Agent URL, for example `http://host.docker.internal:8015`
- `IOS_APPIUM_HOST` - Optional Mac Appium XCUITest URL for `test-svc` and `test-worker`
- `IOS_XCODE_ORG_ID`, `IOS_XCODE_SIGNING_ID`, `IOS_WDA_BUNDLE_ID`, `IOS_ALLOW_PROVISIONING_DEVICE_REGISTRATION` - Optional iOS WDA signing settings for script execution
- `DEVICE_SCAN_INTERVAL` - Device scan interval in seconds
