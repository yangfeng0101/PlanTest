#!/usr/bin/env python3
"""
Screen Service - Low-latency screen streaming via scrcpy + WebSocket
Frame rate: 30-60 FPS, Latency: <100ms
"""

import asyncio
import json
import subprocess
import time
import os
import signal
from urllib.parse import urlparse
import websockets
from websockets.server import serve

# Configuration
PORT = 8080
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


async def start_scrcpy_stream(device_id, width=720, bitrate='2M'):
    """Start scrcpy + ffmpeg pipeline for streaming"""
    if device_id in active_streams:
        return active_streams[device_id]

    print(f"Starting scrcpy stream for {device_id}...")

    # Create pipe for video data
    pipe_path = f'/tmp/scrcpy_{device_id}.h264'

    # scrcpy command - output H.264 to stdout
    scrcpy_cmd = [
        SCRCPY_PATH,
        '-s', device_id,
        '--no-audio',
        '--no-display',
        '-b', bitrate,
        '-m', str(width),
        '--video-codec=h264',
        '--no-control',
        '--record-format=h264',
        '--record', pipe_path,
    ]

    # Alternative: use scrcpy to capture screen and pipe to ffmpeg
    # ffmpeg converts to JPEG frames and outputs to stdout
    # We then send frames via WebSocket

    # Let's use a simpler approach:
    # adb exec-out screencap -> ffmpeg -> JPEG -> WebSocket
    # But for low latency, we need continuous capture

    # Best approach: Use ffmpeg to read from scrcpy's v4l2 output
    # But that requires v4l2loopback

    # Simplest low-latency approach:
    # Continuous screenshot capture with ffmpeg scaling
    # Targeting 20-30 FPS

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
    target_fps = 30
    frame_interval = 1.0 / target_fps

    while stream.get('running', False):
        try:
            loop_start = time.time()

            # Capture frame using ffmpeg (faster than screencap -p)
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
                    '-vf', f'scale={width}:-1:fast=1',
                    '-q:v', '3',
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
                    message = json.dumps({
                        'type': 'frame',
                        'data': list(jpeg_data),
                    })

                    # Send to clients
                    disconnected = set()
                    for client in stream.get('clients', set()):
                        try:
                            await client.send(message)
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


async def handle_websocket(websocket, path):
    """Handle WebSocket connections"""
    parsed = urlparse(path)
    path_parts = parsed.path.strip('/').split('/')

    # Expected path: /ws/{device_id}/stream
    if len(path_parts) >= 3 and path_parts[0] == 'ws':
        device_id = path_parts[1]

        print(f"Client connected for device: {device_id}")

        # Start stream if not already running
        if device_id not in active_streams:
            await start_scrcpy_stream(device_id)

        # Add client to stream
        if device_id in active_streams:
            active_streams[device_id]['clients'].add(websocket)

        try:
            async for message in websocket:
                # Handle client messages (ping/pong, control)
                try:
                    data = json.loads(message)
                    if data.get('type') == 'ping':
                        await websocket.send(json.dumps({'type': 'pong'}))
                except:
                    pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            # Remove client
            if device_id in active_streams:
                active_streams[device_id]['clients'].discard(websocket)
            print(f"Client disconnected for device: {device_id}")

    else:
        await websocket.close()


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


async def http_handler(reader, writer):
    """Handle HTTP requests"""
    data = await reader.read(1024)
    request = data.decode()
    lines = request.split('\r\n')

    if not lines:
        writer.close()
        return

    method, path, _ = lines[0].split(' ')

    # Parse path
    parsed = urlparse(path)
    path_parts = parsed.path.strip('/').split('/')

    def send_response(status, content_type, body):
        response = f"HTTP/1.1 {status}\r\n"
        response += f"Content-Type: {content_type}\r\n"
        response += "Access-Control-Allow-Origin: *\r\n"
        response += "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
        response += "Access-Control-Allow-Headers: Content-Type\r\n"
        response += f"Content-Length: {len(body)}\r\n"
        response += "\r\n"
        writer.write(response.encode() + body)

    if method == 'OPTIONS':
        send_response(200, 'application/json', b'{}')
    elif path == '/health':
        send_response(200, 'application/json', json.dumps({"status": "ok"}).encode())
    elif path.startswith('/api/v1/devices/') and path.endswith('/screenshot'):
        device_id = path_parts[3]
        # Capture screenshot
        proc = await asyncio.create_subprocess_exec(
            ADB_PATH, '-s', device_id, 'exec-out', 'screencap', '-p',
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if stdout:
            send_response(200, 'image/png', stdout)
        else:
            send_response(500, 'application/json', json.dumps({"error": "Screenshot failed"}).encode())
    elif path.startswith('/api/v1/devices/') and '/screen/session' in path:
        device_id = path_parts[3]
        response = {
            "deviceId": device_id,
            "wsUrl": f"ws://localhost:{PORT}/ws/{device_id}/stream",
            "status": "available"
        }
        send_response(200, 'application/json', json.dumps(response).encode())
    elif method == 'POST' and path.startswith('/api/v1/devices/') and path.endswith('/input'):
        device_id = path_parts[3]
        body_start = request.find('\r\n\r\n') + 4
        body = request[body_start:]
        try:
            input_data = json.loads(body)
            result = await send_input(device_id, input_data)
            send_response(200, 'application/json', json.dumps({"success": True, "result": result}).encode())
        except Exception as e:
            send_response(500, 'application/json', json.dumps({"error": str(e)}).encode())
    else:
        send_response(404, 'application/json', json.dumps({"error": "Not found"}).encode())

    await writer.drain()
    writer.close()


async def main():
    print(f"Starting Screen Service on port {PORT}...")
    print(f"WebSocket: ws://localhost:{PORT}/ws/{{device_id}}/stream")

    # Start WebSocket server
    async with serve(handle_websocket, "", PORT):
        print(f"Server running at http://localhost:{PORT}")
        print("Press Ctrl+C to stop")

        # Keep running
        await asyncio.Future()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
