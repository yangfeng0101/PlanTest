require('dotenv/config');

const http = require('http');
const { AndroidAgent, AndroidDevice } = require('@midscene/android');

const PORT = Number(process.env.PORT || 8005);
const MODEL_ENV_KEYS = [
  'MIDSCENE_MODEL_NAME',
  'MIDSCENE_MODEL_BASE_URL',
  'MIDSCENE_MODEL_API_KEY',
  'MIDSCENE_MODEL_FAMILY',
];
const agentCache = new Map();

function jsonResponse(res, statusCode, body) {
  const payload = JSON.stringify(body);
  res.writeHead(statusCode, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(payload),
  });
  res.end(payload);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => {
      chunks.push(chunk);
      if (Buffer.concat(chunks).length > 1024 * 1024) {
        reject(new Error('Request body is too large'));
        req.destroy();
      }
    });
    req.on('end', () => {
      try {
        const text = Buffer.concat(chunks).toString('utf8');
        resolve(text ? JSON.parse(text) : {});
      } catch (error) {
        reject(new Error(`Invalid JSON: ${error.message}`));
      }
    });
    req.on('error', reject);
  });
}

function requireModelConfig() {
  const missing = MODEL_ENV_KEYS.filter((key) => !process.env[key]);
  if (missing.length > 0) {
    throw new Error(`Midscene model is not configured. Missing env: ${missing.join(', ')}`);
  }
}

function buildDeviceOptions() {
  const options = {};
  if (process.env.MIDSCENE_ADB_REMOTE_HOST) {
    options.remoteAdbHost = process.env.MIDSCENE_ADB_REMOTE_HOST;
  }
  if (process.env.MIDSCENE_ADB_REMOTE_PORT) {
    options.remoteAdbPort = Number(process.env.MIDSCENE_ADB_REMOTE_PORT);
  }
  if (process.env.MIDSCENE_ANDROID_ADB_PATH) {
    options.androidAdbPath = process.env.MIDSCENE_ANDROID_ADB_PATH;
  }
  return options;
}

async function getAgent(deviceId) {
  const cached = agentCache.get(deviceId);
  if (cached) {
    return cached.agent;
  }

  const device = new AndroidDevice(deviceId, buildDeviceOptions());
  await device.connect();

  const agent = new AndroidAgent(device, {
    generateReport: false,
    autoPrintReportMsg: false,
    cacheId: process.env.MIDSCENE_CACHE === 'true' ? `device-farm-${deviceId}` : undefined,
    aiActContext: process.env.MIDSCENE_AI_ACT_CONTEXT || undefined,
  });

  const entry = { device, agent };
  agentCache.set(deviceId, entry);
  return agent;
}

async function rebuildAgent(deviceId) {
  await destroyAgent(deviceId);
  return getAgent(deviceId);
}

async function destroyAgent(deviceId) {
  const cached = agentCache.get(deviceId);
  agentCache.delete(deviceId);
  if (cached?.device && typeof cached.device.destroy === 'function') {
    try {
      await cached.device.destroy();
    } catch (error) {
      console.warn(`Failed to destroy Android device for ${deviceId}: ${error.message}`);
    }
  }
}

function withTimeout(promise, timeoutMs, onTimeout) {
  if (!timeoutMs || timeoutMs <= 0) {
    return promise;
  }

  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      if (onTimeout) {
        onTimeout();
      }
      reject(new Error(`AI operation timed out after ${timeoutMs}ms`));
    }, timeoutMs);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function optionsFromPayload(payload) {
  return {
    deepLocate: Boolean(payload.deep_locate),
  };
}

function compactOptions(options) {
  return Object.fromEntries(Object.entries(options).filter(([, value]) => value !== undefined && value !== null));
}

async function withDevicePixelRatio(agent, result) {
  if (!result || result.dpr) {
    return result;
  }

  const getDensity = agent.interface?.getDisplayDensity;
  if (typeof getDensity !== 'function') {
    return result;
  }

  try {
    const density = await getDensity.call(agent.interface);
    return {
      ...result,
      dpr: density ? density / 160 : undefined,
    };
  } catch (error) {
    return result;
  }
}

async function executeOperation(agent, operation, payload, timeoutMs, abortSignal) {
  const baseOptions = {
    ...optionsFromPayload(payload),
    abortSignal,
  };
  const run = async () => {
    switch (operation) {
      case 'ai':
        return agent.ai(payload.instruction, { abortSignal });
      case 'ai_act':
        return agent.aiAct(payload.instruction, baseOptions);
      case 'ai_locate':
        return withDevicePixelRatio(agent, await agent.aiLocate(payload.target, baseOptions));
      case 'ai_tap':
        return agent.aiTap(payload.target, baseOptions);
      case 'ai_input':
        return agent.aiInput(payload.target, {
          value: payload.text,
          mode: payload.mode || 'replace',
          ...baseOptions,
        });
      case 'ai_clear':
        return agent.aiClearInput(payload.target, baseOptions);
      case 'ai_key':
        if (payload.target) {
          return agent.aiKeyboardPress(payload.target, {
            keyName: payload.key,
            ...baseOptions,
          });
        }
        return agent.aiKeyboardPress(payload.key, undefined, { abortSignal });
      case 'ai_scroll':
        return agent.aiScroll(payload.target || undefined, compactOptions({
          scrollType: payload.scroll_type || 'singleAction',
          direction: payload.direction || 'down',
          distance: payload.distance,
          ...baseOptions,
        }));
      case 'ai_long_press':
        return agent.aiLongPress(payload.target, compactOptions({
          duration: payload.duration,
          ...baseOptions,
        }));
      case 'ai_double_tap':
        return agent.aiDoubleClick(payload.target, baseOptions);
      case 'ai_wait':
        await agent.aiWaitFor(payload.assertion, {
          timeoutMs,
          checkIntervalMs: payload.check_interval_ms || 3000,
          abortSignal,
        });
        return true;
      case 'ai_assert': {
        const assertionResult = await agent.aiAssert(
          payload.assertion,
          payload.error_message || undefined,
          { abortSignal, keepRawResponse: true },
        );
        if (assertionResult?.pass === false) {
          throw new Error(assertionResult.message || payload.error_message || 'AI assertion failed');
        }
        return assertionResult;
      }
      default:
        throw new Error(`Unsupported AI operation: ${operation}`);
    }
  };

  return run();
}

async function handleExecute(req, res) {
  const startedAt = Date.now();
  let body;
  try {
    body = await readJson(req);
  } catch (error) {
    jsonResponse(res, 400, { success: false, error: error.message });
    return;
  }

  const { task_id: taskId, device_id: deviceId, operation, payload = {}, timeout_ms: timeoutMs = 30000 } = body;
  if (!taskId || !deviceId || !operation) {
    jsonResponse(res, 400, {
      success: false,
      error: 'task_id, device_id and operation are required',
    });
    return;
  }

  try {
    requireModelConfig();
    let agent = await getAgent(deviceId);
    let result;
    const abortController = new AbortController();
    const runWithTimeout = () => withTimeout(
      executeOperation(agent, operation, payload, timeoutMs, abortController.signal),
      timeoutMs,
      () => {
        abortController.abort();
        void destroyAgent(deviceId);
      },
    );

    try {
      result = await runWithTimeout();
    } catch (error) {
      if (/device|adb|scrcpy|connect|closed|disconnect/i.test(error.message)) {
        agent = await rebuildAgent(deviceId);
        result = await runWithTimeout();
      } else {
        throw error;
      }
    }

    jsonResponse(res, 200, {
      success: true,
      operation,
      result: result ?? null,
      error: null,
      duration_ms: Date.now() - startedAt,
    });
  } catch (error) {
    const message = error?.message || String(error);
    console.error(`[${taskId}] ${operation} failed on ${deviceId}: ${message}`);
    jsonResponse(res, 500, {
      success: false,
      operation,
      result: null,
      error: message,
      duration_ms: Date.now() - startedAt,
    });
  }
}

const server = http.createServer(async (req, res) => {
  if (req.method === 'GET' && req.url === '/health') {
    jsonResponse(res, 200, {
      status: 'healthy',
      service: 'midscene-runner',
      model_configured: MODEL_ENV_KEYS.every((key) => Boolean(process.env[key])),
    });
    return;
  }

  if (req.method === 'POST' && req.url === '/api/v1/ai/execute') {
    await handleExecute(req, res);
    return;
  }

  jsonResponse(res, 404, { success: false, error: 'Not found' });
});

process.on('SIGTERM', () => {
  server.close(() => process.exit(0));
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`midscene-runner listening on ${PORT}`);
});
