/**
 * Screen Service - Real-time streaming via scrcpy
 * Uses scrcpy for low-latency H.264 capture, converts to MJPEG via ffmpeg
 * Target: 30 FPS, <100ms latency
 */

const { spawn, execSync } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const { URL } = require('url');
const fs = require('fs');
const path = require('path');

const PORT = 8080;
const ADB_PATH = '/opt/homebrew/bin/adb';
const SCRCPY_PATH = '/opt/homebrew/bin/scrcpy';
const FFMPEG_PATH = '/opt/homebrew/bin/ffmpeg';

// Active streams
const activeStreams = new Map();

// HTTP Server
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname;

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  if (path === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', service: 'screen-svc' }));
    return;
  }

  if (path.match(/^\/api\/v1\/devices\/[^/]+\/screen\/session$/)) {
    const deviceId = path.split('/')[4];
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      deviceId,
      wsUrl: `ws://localhost:${PORT}/ws/${deviceId}`,
      status: 'available'
    }));
    return;
  }

  if (path.match(/^\/api\/v1\/devices\/[^/]+\/input$/) && req.method === 'POST') {
    const deviceId = path.split('/')[4];
    await handleInput(req, res, deviceId);
    return;
  }

  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Not found' }));
});

// WebSocket Server
const wss = new WebSocket.Server({ server });

wss.on('connection', (ws, req) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const pathParts = url.pathname.split('/').filter(Boolean);

  if (pathParts.length >= 2 && pathParts[0] === 'ws') {
    const deviceId = pathParts[1];
    console.log(`[WS] Client connected: ${deviceId}`);
    startScrcpyStreaming(deviceId, ws);

    ws.on('message', (message) => {
      try {
        const data = JSON.parse(message);
        if (data.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }));
        }
      } catch (e) {}
    });

    ws.on('close', () => stopStreaming(deviceId, ws));
    ws.on('error', () => stopStreaming(deviceId, ws));
  } else {
    ws.close();
  }
});

// Start scrcpy + ffmpeg pipeline
function startScrcpyStreaming(deviceId, ws) {
  if (!activeStreams.has(deviceId)) {
    const videoFile = `/tmp/scrcpy_${deviceId}.mkv`;

    // Clean up old file
    try { fs.unlinkSync(videoFile); } catch (e) {}

    const stream = {
      clients: new Set(),
      running: true,
      fps: 0,
      frameCount: 0,
      lastFpsTime: Date.now(),
      scrcpy: null,
      ffmpeg: null,
      videoFile
    };
    activeStreams.set(deviceId, stream);

    // Wake up and unlock device screen
    console.log(`[ADB] Waking up device ${deviceId}...`);
    execSync(`${ADB_PATH} -s ${deviceId} shell "input keyevent KEYCODE_WAKEUP"`, { timeout: 5000 });
    execSync(`${ADB_PATH} -s ${deviceId} shell "input swipe 500 1500 500 500 200"`, { timeout: 5000 });
    console.log(`[ADB] Screen unlocked`);

    // Start scrcpy recording to file
    // Use --no-window instead of --no-playback (no-playback causes empty recording on macOS)
    console.log(`[scrcpy] Starting for ${deviceId}...`);
    stream.scrcpy = spawn(SCRCPY_PATH, [
      '-s', deviceId,
      '--no-window',
      '--no-audio',
      '--video-codec=h264',
      '--max-size=720',
      '--max-fps=30',
      `--record=${videoFile}`,
      '--no-control'
    ]);

    stream.scrcpy.on('error', (e) => console.error(`[scrcpy] Error: ${e}`));
    stream.scrcpy.stderr.on('data', (data) => {
      const msg = data.toString();
      if (msg.includes('INFO') || msg.includes('ERROR')) {
        console.log(`[scrcpy] ${msg.trim()}`);
      }
    });

    // Wait for video file to have content, then start ffmpeg
    const checkAndStartFFmpeg = () => {
      if (!stream.running) return;

      try {
        const stats = fs.statSync(videoFile);
        if (stats.size > 50000) {  // Need at least 50KB for ffmpeg to start
          console.log(`[ffmpeg] Starting MJPEG conversion for ${deviceId} (file size: ${stats.size})...`);
          startFFmpeg(stream, deviceId);
        } else {
          console.log(`[scrcpy] Waiting for video data... (${stats.size} bytes)`);
          setTimeout(checkAndStartFFmpeg, 1000);
        }
      } catch (e) {
        setTimeout(checkAndStartFFmpeg, 500);
      }
    };

    setTimeout(checkAndStartFFmpeg, 3000);  // Wait 3s for scrcpy to initialize
  }

  activeStreams.get(deviceId).clients.add(ws);
}

function startFFmpeg(stream, deviceId) {
  // Optimized ffmpeg for real-time streaming
  // -re removed for faster processing
  stream.ffmpeg = spawn(FFMPEG_PATH, [
    '-i', stream.videoFile,
    '-vf', 'scale=480:-1',
    '-q:v', '8',
    '-f', 'mjpeg',
    '-'
  ]);

  let buffer = Buffer.alloc(0);
  const JPEG_START = Buffer.from([0xff, 0xd8]);
  const JPEG_END = Buffer.from([0xff, 0xd9]);

  stream.ffmpeg.stdout.on('data', (chunk) => {
    if (!stream.running) return;

    buffer = Buffer.concat([buffer, chunk]);

    // Find complete JPEG frames
    while (true) {
      const startIdx = buffer.indexOf(JPEG_START);
      if (startIdx === -1) {
        buffer = Buffer.alloc(0);
        break;
      }

      const endIdx = buffer.indexOf(JPEG_END, startIdx);
      if (endIdx === -1) break;

      // Extract frame
      const frame = buffer.slice(startIdx, endIdx + 2);
      buffer = buffer.slice(endIdx + 2);

      // Broadcast frame
      if (stream.clients.size > 0) {
        stream.frameCount++;
        const now = Date.now();
        if (now - stream.lastFpsTime >= 1000) {
          stream.fps = stream.frameCount;
          stream.frameCount = 0;
          stream.lastFpsTime = now;
        }

        const message = JSON.stringify({
          type: 'frame',
          data: frame.toString('base64'),
          fps: stream.fps
        });
        stream.clients.forEach(client => {
          if (client.readyState === WebSocket.OPEN) {
            client.send(message);
          }
        });
      }
    }
  });

  stream.ffmpeg.on('error', (e) => console.error(`[ffmpeg] Error: ${e}`));
  stream.ffmpeg.on('close', () => {
    console.log(`[ffmpeg] Closed for ${deviceId}`);
    // Restart if still running
    if (stream.running) {
      setTimeout(() => {
        if (stream.running && fs.existsSync(stream.videoFile)) {
          const stats = fs.statSync(stream.videoFile);
          if (stats.size > 10000) {
            console.log(`[ffmpeg] Restarting for ${deviceId}...`);
            startFFmpeg(stream, deviceId);
          }
        }
      }, 1000);
    }
  });
}

function stopStreaming(deviceId, ws) {
  const stream = activeStreams.get(deviceId);
  if (stream) {
    stream.clients.delete(ws);
    if (stream.clients.size === 0) {
      stream.running = false;
      if (stream.scrcpy) stream.scrcpy.kill();
      if (stream.ffmpeg) stream.ffmpeg.kill();
      try { fs.unlinkSync(stream.videoFile); } catch (e) {}
      activeStreams.delete(deviceId);
      console.log(`[Stream] Stopped: ${deviceId}`);
    }
  }
}

// HTTP handlers
async function handleInput(req, res, deviceId) {
  let body = '';
  req.on('data', chunk => body += chunk);
  req.on('end', async () => {
    try {
      const data = JSON.parse(body);
      const result = await sendInput(deviceId, data);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ success: true, result }));
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    }
  });
}

async function sendInput(deviceId, data) {
  return new Promise((resolve, reject) => {
    let cmd;
    const type = data.type || 'tap';
    const x = Math.round(data.x || 0);
    const y = Math.round(data.y || 0);

    if (type === 'tap') {
      cmd = [ADB_PATH, '-s', deviceId, 'shell', 'input', 'tap', String(x), String(y)];
    } else if (type === 'swipe') {
      const x2 = Math.round(data.x2 || x);
      const y2 = Math.round(data.y2 || y);
      cmd = [ADB_PATH, '-s', deviceId, 'shell', 'input', 'swipe',
        String(x), String(y), String(x2), String(y2), String(data.duration || 150)];
    } else if (type === 'key') {
      cmd = [ADB_PATH, '-s', deviceId, 'shell', 'input', 'keyevent', data.keycode || 'KEYCODE_HOME'];
    } else if (type === 'text') {
      cmd = [ADB_PATH, '-s', deviceId, 'shell', 'input', 'text', (data.text || '').replace(/ /g, '%s')];
    } else {
      return reject(new Error('Unknown input type'));
    }

    const proc = spawn(cmd[0], cmd.slice(1));
    proc.on('close', () => resolve('ok'));
    proc.on('error', (e) => reject(e));
  });
}

server.listen(PORT, () => {
  console.log(`Screen Service (scrcpy) running at http://localhost:${PORT}`);
  console.log(`WebSocket: ws://localhost:${PORT}/ws/{deviceId}`);
});

process.on('SIGINT', () => {
  console.log('\nShutting down...');
  activeStreams.forEach((stream) => {
    stream.running = false;
    if (stream.scrcpy) stream.scrcpy.kill();
    if (stream.ffmpeg) stream.ffmpeg.kill();
    try { fs.unlinkSync(stream.videoFile); } catch (e) {}
  });
  process.exit(0);
});
