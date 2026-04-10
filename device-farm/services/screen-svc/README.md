# Screen Service

Screen mirroring and remote control service using scrcpy and WebRTC.

## Features

- Real-time screen mirroring via scrcpy
- WebRTC-based low latency streaming
- Remote touch and key input
- Multi-client support

## Prerequisites

- Go 1.21+
- scrcpy installed on host
- ADB access to Android devices

## Running

```bash
go run ./cmd
```

## API Endpoints

### REST API

- `GET /api/v1/health` - Health check
- `GET /api/v1/sessions` - List active sessions
- `GET /api/v1/sessions/:device_id` - Get session details
- `POST /api/v1/sessions/:device_id/start` - Start screen session
- `POST /api/v1/sessions/:device_id/stop` - Stop screen session
- `POST /api/v1/sessions/:device_id/touch` - Send touch event
- `POST /api/v1/sessions/:device_id/key` - Send key event
- `POST /api/v1/sessions/:device_id/text` - Send text input

### WebSocket

- `WS /ws/screen/:device_id` - Screen stream and control
- `WS /webrtc/:device_id` - WebRTC signaling

## Configuration

Edit `config/config.yaml` for customization.
