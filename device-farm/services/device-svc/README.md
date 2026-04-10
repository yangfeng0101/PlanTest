# Device Service

Device management service for Android devices via ADB.

## Features

- Device discovery and monitoring
- Device status tracking
- Device occupation/release
- Screenshot capture
- Shell command execution
- Real-time WebSocket updates

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
- `DEVICE_SCAN_INTERVAL` - Device scan interval in seconds
