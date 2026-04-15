#!/usr/bin/env python3
"""
Screen Service - Low-latency screen streaming via WebSocket + MJPEG
Frame rate: 20-30 FPS, Latency: <200ms
"""

import asyncio
import json
import subprocess
import time
import os
import signal
import base64
from aiohttp import web, WSMsgType

# Configuration
PORT = 8002
ADB_PATH = "/opt/homebrew/bin/adb"
SCRCPY_PATH = "/opt/homebrew/bin/scrcpy"
FFMPEG_PATH = "/opt/homebrew/bin/ffmpeg"

# Active streams
active_streams = {}
connected_clients = set()


def get_connected_devices():
    """Get list of connected device IDs"""
    try:
        result = subprocess.run(
            [ADB_PATH, "devices"],
            capture_output=True, text=True, timeout=5
        )
        devices = []
        for line in result.stdout.strip().split('\n')[1:]:
            if '\t' in line:
                device_id, status = line.split('\t')
                if status == 'device':
                    devices.append(device_id)
        return devices
    except:
        return []


async def start_scrcpy_stream(device_id, width=720):
    """Start screen capture stream for device"""
    if device_id in active_streams:
        return active_streams[device_id]

    print(f"Starting stream for {device_id}...")

    stream_info = {
        'device_id': device_id,
        'width': width,
        'running': True,
        'clients': set(),
        'last_frame': None,
        'frame_count': 0,
    }

    active_streams[device_id] = stream_info

    # Start frame capture task
    asyncio.create_task(capture_frames_task(device_id, width))

    return stream_info


async def capture_frames_task(device_id, width=720):
    """Background task to capture and broadcast frames"""
    if device_id not in active_streams:
        return

    stream = active_streams[device_id]
    target_fps = 20
    frame_interval = 1.0 / target_fps

    while stream.get('running', False):
        try:
            loop_start = time.time()

            # Capture frame using adb screencap
            proc = await asyncio.create_subprocess_exec(
                ADB_PATH, '-s', device_id, 'exec-out',
                'screencap', '-p',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )

            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=1.0)

            if stdout and len(stdout) > 1000:
                # Scale and convert to JPEG using ffmpeg
                ffmpeg_proc = await asyncio.create_subprocess_exec(
                    FFMPEG_PATH,
                    '-i', '-',
                    '-vf', f'scale={width}:-1',
                    '-q:v', '5',
                    '-f', 'mjpeg',
                    '-',
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL
                )

                jpeg_data, _ = await asyncio.wait_for(
                    ffmpeg_proc.communicate(input=stdout),
                    timeout=0.5
                )

                if jpeg_data and len(jpeg_data) > 1000:
                    stream['last_frame'] = jpeg_data
                    stream['frame_count'] += 1

                    # Broadcast to all connected clients for this device
                    # Send as JSON with base64 encoded image
                    disconnected = set()
                    for client in stream.get('clients', set()):
                        try:
                            # Send as JSON message with base64 encoded image
                            message = json.dumps({
                                'type': 'frame',
                                'data': base64.b64encode(jpeg_data).decode('utf-8')
                            })
                            await client.send_str(message)
                        except:
                            disconnected.add(client)

                    for client in disconnected:
                        stream['clients'].discard(client)

            # Maintain frame rate
            elapsed = time.time() - loop_start
            sleep_time = max(0, frame_interval - elapsed)
            await asyncio.sleep(sleep_time)

        except asyncio.TimeoutError:
            continue
        except Exception as e:
            print(f"Frame capture error: {e}")
            await asyncio.sleep(0.1)


async def stop_scrcpy_stream(device_id):
    """Stop streaming for a device"""
    if device_id in active_streams:
        active_streams[device_id]['running'] = False
        del active_streams[device_id]
        print(f"Stopped stream for {device_id}")


async def send_input(device_id, input_data):
    """Send touch/key input to device"""
    input_type = input_data.get('type', 'tap')
    x = input_data.get('x', 0)
    y = input_data.get('y', 0)

    if input_type == 'tap':
        cmd = [ADB_PATH, '-s', device_id, 'shell', 'input', 'tap', str(int(x)), str(int(y))]
    elif input_type == 'swipe':
        x2 = input_data.get('x2', x)
        y2 = input_data.get('y2', y)
        duration = input_data.get('duration', 150)
        cmd = [ADB_PATH, '-s', device_id, 'shell', 'input', 'swipe',
               str(int(x)), str(int(y)), str(int(x2)), str(int(y2)), str(duration)]
    elif input_type == 'key':
        keycode = input_data.get('keycode', 'KEYCODE_HOME')
        cmd = [ADB_PATH, '-s', device_id, 'shell', 'input', 'keyevent', keycode]
    elif input_type == 'text':
        text = input_data.get('text', '')
        text = text.replace(' ', '%s')
        cmd = [ADB_PATH, '-s', device_id, 'shell', 'input', 'text', text]
    else:
        return "Unknown input type"

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return "ok"


# HTTP Handlers
async def handle_health(request):
    """Health check endpoint"""
    return web.json_response({"status": "ok"})


async def handle_screenshot(request):
    """Screenshot endpoint"""
    device_id = request.match_info.get('device_id')

    proc = await asyncio.create_subprocess_exec(
        ADB_PATH, '-s', device_id, 'exec-out', 'screencap', '-p',
        stdout=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()

    if stdout:
        return web.Response(body=stdout, content_type='image/png')
    else:
        return web.json_response({"error": "Screenshot failed"}, status=500)


async def handle_session(request):
    """Get screen session info"""
    device_id = request.match_info.get('device_id')

    response = {
        "deviceId": device_id,
        "wsUrl": f"ws://localhost:{PORT}/ws/{device_id}/stream",
        "status": "available"
    }
    return web.json_response(response)


async def handle_input(request):
    """Handle touch/key input"""
    device_id = request.match_info.get('device_id')

    try:
        input_data = await request.json()
        result = await send_input(device_id, input_data)
        return web.json_response({"success": True, "result": result})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# WebSocket Handler
async def handle_websocket(request):
    """Handle WebSocket connections for screen streaming"""
    device_id = request.match_info.get('device_id')

    print(f"WebSocket client connected for device: {device_id}")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Start stream if not already running
    if device_id not in active_streams:
        await start_scrcpy_stream(device_id)

    # Add client to stream
    if device_id in active_streams:
        active_streams[device_id]['clients'].add(ws)

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if data.get('type') == 'ping':
                        await ws.send_json({'type': 'pong'})
                except:
                    pass
            elif msg.type == WSMsgType.ERROR:
                print(f"WebSocket error: {ws.exception()}")
    finally:
        # Remove client
        if device_id in active_streams:
            active_streams[device_id]['clients'].discard(ws)
        print(f"WebSocket client disconnected for device: {device_id}")

    return ws


def create_app():
    """Create aiohttp application"""
    app = web.Application()

    # CORS middleware
    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == 'OPTIONS':
            response = web.Response()
        else:
            response = await handler(request)

        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    app = web.Application(middlewares=[cors_middleware])

    # Routes
    app.router.add_get('/health', handle_health)
    app.router.add_get('/api/v1/devices/{device_id}/screenshot', handle_screenshot)
    app.router.add_get('/api/v1/devices/{device_id}/screen/session', handle_session)
    app.router.add_post('/api/v1/devices/{device_id}/input', handle_input)
    app.router.add_get('/ws/{device_id}/stream', handle_websocket)

    return app


if __name__ == '__main__':
    print(f"Starting Screen Service on port {PORT}...")
    print(f"WebSocket: ws://localhost:{PORT}/ws/{{device_id}}/stream")
    print(f"HTTP API: http://localhost:{PORT}/api/v1/...")
    print(f"Health: http://localhost:{PORT}/health")

    app = create_app()
    web.run_app(app, host='0.0.0.0', port=PORT, print=None)
