/**
 * Screen Service - Parallel capture for higher FPS
 *
 * Uses overlapping capture requests to maximize throughput
 */

const { spawn } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const { URL } = require('url');

const PORT = 8080;
const ADB_PATH = '/opt/homebrew/bin/adb';
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

  if (path.match(/^\/api\/v1\/devices\/[^/]+\/screenshot$/)) {
    const deviceId = path.split('/')[4];
    await handleScreenshot(req, res, deviceId);
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
    startStreaming(deviceId, ws);

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

// Streaming functions
function startStreaming(deviceId, ws) {
  if (!activeStreams.has(deviceId)) {
    const stream = {
      clients: new Set(),
      running: true,
      lastFrame: null,
      fps: 0,
      frameCount: 0,
      lastFpsTime: Date.now(),
      pendingCaptures: 0,
      maxPending: 3  // Allow 3 parallel captures for better FPS
    };
    activeStreams.set(deviceId, stream);

    // Start capture
    for (let i = 0; i < stream.maxPending; i++) {
      setTimeout(() => captureFrame(deviceId), i * 200);
    }
  }

  activeStreams.get(deviceId).clients.add(ws);
}

function stopStreaming(deviceId, ws) {
  const stream = activeStreams.get(deviceId);
  if (stream) {
    stream.clients.delete(ws);
    if (stream.clients.size === 0) {
      stream.running = false;
      activeStreams.delete(deviceId);
      console.log(`[Stream] Stopped: ${deviceId}`);
    }
  }
}

// Capture frame with pipeline
function captureFrame(deviceId) {
  const stream = activeStreams.get(deviceId);
  if (!stream || !stream.running) {
    console.log(`[captureFrame] No stream or not running for ${deviceId}`);
    return;
  }

  // Limit parallel captures
  if (stream.pendingCaptures >= stream.maxPending) {
    // Schedule retry
    setTimeout(() => captureFrame(deviceId), 50);
    return;
  }

  stream.pendingCaptures++;

  const ffmpeg = spawn(FFMPEG_PATH, [
    '-i', '-',
    '-vf', 'scale=320:-1',
    '-q:v', '5',
    '-f', 'mjpeg',
    '-'
  ]);

  const adb = spawn(ADB_PATH, [
    '-s', deviceId,
    'exec-out', 'screencap', '-p'
  ]);

  adb.stdout.pipe(ffmpeg.stdin, { end: true });

  const chunks = [];
  ffmpeg.stdout.on('data', (chunk) => chunks.push(chunk));

  let resolved = false;

  const done = () => {
    if (resolved) return;
    resolved = true;

    stream.pendingCaptures--;

    if (chunks.length > 0 && stream.running) {
      const frame = Buffer.concat(chunks);
      stream.lastFrame = frame;
      stream.frameCount++;

      // Calculate FPS
      const now = Date.now();
      if (now - stream.lastFpsTime >= 1000) {
        stream.fps = stream.frameCount;
        stream.frameCount = 0;
        stream.lastFpsTime = now;
      }

      // Broadcast
      if (stream.clients.size > 0) {
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

    // Schedule next capture immediately
    if (stream.running) {
      setImmediate(() => captureFrame(deviceId));
    }
  };

  ffmpeg.on('close', done);
  ffmpeg.on('error', done);

  // Timeout
  setTimeout(() => {
    try { adb.kill(); ffmpeg.kill(); } catch (e) {}
    done();
  }, 2000);

  adb.on('error', () => { ffmpeg.kill(); done(); });
}

// HTTP handlers
async function handleScreenshot(req, res, deviceId) {
  return new Promise((resolve) => {
    const adb = spawn(ADB_PATH, ['-s', deviceId, 'exec-out', 'screencap', '-p']);
    const chunks = [];
    adb.stdout.on('data', (chunk) => chunks.push(chunk));
    adb.on('close', (code) => {
      if (code === 0 && chunks.length > 0) {
        res.writeHead(200, { 'Content-Type': 'image/png' });
        res.end(Buffer.concat(chunks));
      } else {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Screenshot failed' }));
      }
      resolve();
    });
    adb.on('error', () => {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'ADB error' }));
      resolve();
    });
  });
}

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
  console.log(`Screen Service running at http://localhost:${PORT}`);
  console.log(`WebSocket: ws://localhost:${PORT}/ws/{deviceId}`);
});

process.on('SIGINT', () => {
  console.log('\nShutting down...');
  activeStreams.forEach((stream) => { stream.running = false; });
  process.exit(0);
});
