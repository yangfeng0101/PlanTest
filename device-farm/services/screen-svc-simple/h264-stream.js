/**
 * Screen Service - H.264 streaming via MSE
 * 直接传输 H.264 NAL 单元，前端用 MSE 解码
 */

const { spawn, execSync } = require('child_process');
const http = require('http');
const WebSocket = require('ws');
const { URL } = require('url');
const fs = require('fs');

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
    res.end(JSON.stringify({ status: 'ok', service: 'screen-svc-h264' }));
    return;
  }

  if (path.match(/^\/api\/v1\/devices\/[^/]+\/screen\/session$/)) {
    const deviceId = path.split('/')[4];
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      deviceId,
      wsUrl: `ws://localhost:${PORT}/ws/${deviceId}`,
      status: 'available',
      codec: 'h264'
    }));
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
    startH264Streaming(deviceId, ws);

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

// Start H.264 streaming
function startH264Streaming(deviceId, ws) {
  if (!activeStreams.has(deviceId)) {
    const videoFile = `/tmp/scrcpy_${deviceId}.mkv`;

    // Clean up old file
    try { fs.unlinkSync(videoFile); } catch (e) {}

    const stream = {
      clients: new Set(),
      running: true,
      scrcpy: null,
      ffmpeg: null,
      videoFile,
      sps: null,
      pps: null,
      frameCount: 0
    };
    activeStreams.set(deviceId, stream);

    // Wake up and unlock screen
    console.log(`[ADB] Waking up device ${deviceId}...`);
    try {
      execSync(`${ADB_PATH} -s ${deviceId} shell "input keyevent KEYCODE_WAKEUP"`, { timeout: 5000 });
      execSync(`${ADB_PATH} -s ${deviceId} shell "input swipe 500 1500 500 500 200"`, { timeout: 5000 });
    } catch (e) {
      console.log(`[ADB] Wake up warning: ${e.message}`);
    }

    // Start scrcpy recording
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

    // Wait for video file then start ffmpeg H.264 extraction
    const checkAndStartFFmpeg = () => {
      if (!stream.running) return;

      try {
        const stats = fs.statSync(videoFile);
        if (stats.size > 50000) {
          console.log(`[ffmpeg] Starting H.264 extraction for ${deviceId} (file size: ${stats.size})...`);
          startH264Extraction(stream, deviceId);
        } else {
          console.log(`[scrcpy] Waiting for video data... (${stats.size} bytes)`);
          setTimeout(checkAndStartFFmpeg, 1000);
        }
      } catch (e) {
        setTimeout(checkAndStartFFmpeg, 500);
      }
    };

    setTimeout(checkAndStartFFmpeg, 3000);
  }

  activeStreams.get(deviceId).clients.add(ws);
}

// Extract H.264 NAL units and send to clients
function startH264Extraction(stream, deviceId) {
  // Use ffmpeg to extract raw H.264 with Annex-B format
  stream.ffmpeg = spawn(FFMPEG_PATH, [
    '-i', stream.videoFile,
    '-c:v', 'copy',
    '-bsf:v', 'h264_mp4toannexb',
    '-f', 'h264',
    '-'
  ]);

  let buffer = Buffer.alloc(0);
  const NAL_START = Buffer.from([0x00, 0x00, 0x00, 0x01]);
  let gotKeyframe = false;
  let pendingFrames = [];

  stream.ffmpeg.stdout.on('data', (chunk) => {
    if (!stream.running) return;

    buffer = Buffer.concat([buffer, chunk]);

    // Parse NAL units
    while (true) {
      const startIdx = buffer.indexOf(NAL_START);
      if (startIdx === -1) {
        buffer = buffer.slice(-3);
        break;
      }

      const nextStartIdx = buffer.indexOf(NAL_START, startIdx + 4);
      if (nextStartIdx === -1) break;

      const nalUnit = buffer.slice(startIdx, nextStartIdx);
      buffer = buffer.slice(nextStartIdx);

      const nalType = nalUnit[4] & 0x1F;

      // 7 = SPS, 8 = PPS, 5 = IDR, 1 = non-IDR
      if (nalType === 7) {
        stream.sps = nalUnit;
        console.log(`[H264] Got SPS`);
      } else if (nalType === 8) {
        stream.pps = nalUnit;
        console.log(`[H264] Got PPS`);
      } else if (nalType === 5) {
        // Keyframe
        gotKeyframe = true;
        stream.frameCount++;

        // Send SPS + PPS + IDR together
        if (stream.sps && stream.pps) {
          const frameData = Buffer.concat([stream.sps, stream.pps, nalUnit]);
          sendFrame(stream, frameData, true);
        }

        // Send pending frames
        pendingFrames.forEach(f => sendFrame(stream, f.data, false));
        pendingFrames = [];
      } else if (nalType === 1) {
        // P-frame
        stream.frameCount++;

        if (gotKeyframe) {
          sendFrame(stream, nalUnit, false);
        } else {
          // Buffer until we get a keyframe
          pendingFrames.push({ data: nalUnit });
        }
      }
    }
  });

  stream.ffmpeg.on('error', (e) => console.error(`[ffmpeg] Error: ${e}`));
  stream.ffmpeg.on('close', () => {
    console.log(`[ffmpeg] Closed for ${deviceId}`);
    if (stream.running) {
      setTimeout(() => {
        if (stream.running && fs.existsSync(stream.videoFile)) {
          const stats = fs.statSync(stream.videoFile);
          if (stats.size > 50000) {
            console.log(`[ffmpeg] Restarting for ${deviceId}...`);
            startH264Extraction(stream, deviceId);
          }
        }
      }, 1000);
    }
  });
}

// Send frame to all clients
function sendFrame(stream, frameData, isKeyframe) {
  if (stream.clients.size > 0) {
    const message = JSON.stringify({
      type: 'nalu',
      data: frameData.toString('base64'),
      isKeyframe: isKeyframe,
      frameNum: stream.frameCount
    });

    stream.clients.forEach(client => {
      if (client.readyState === 1) {
        client.send(message);
      }
    });
  }
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

server.listen(PORT, () => {
  console.log(`H.264 Screen Service running at http://localhost:${PORT}`);
  console.log(`WebSocket: ws://localhost:${PORT}/ws/{deviceId}`);
  console.log(`Codec: H.264 (MSE compatible)`);
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
