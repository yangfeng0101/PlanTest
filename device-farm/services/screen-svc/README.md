# Screen Service

Screen mirroring and remote control service using scrcpy, LiveKit, and WebRTC.

## Features

- Real-time screen mirroring via scrcpy
- LiveKit-based low latency streaming
- Remote touch, key, and text input via WebRTC DataChannel
- Multi-client support

## Prerequisites

- Go 1.21+
- scrcpy installed on host
- ADB access to Android devices
- Reachable LiveKit server

## Running

```bash
go run ./cmd/main.go
```

## API Endpoints

### REST API

- `GET /api/v1/health` - Health check
- `GET /api/v1/sessions/:device_id` - Get session details
- `POST /api/v1/sessions/:device_id/start` - Start screen session
- `POST /api/v1/sessions/:device_id/stop` - Stop screen session

### Control Channel

After `start`, clients join the returned LiveKit room with the returned token. Remote control is sent through LiveKit data messages on `topic=control`.

```json
{ "type": "touch", "action": "move", "x": 120, "y": 360 }
```

## Configuration

Edit `config/config.yaml` for customization.
