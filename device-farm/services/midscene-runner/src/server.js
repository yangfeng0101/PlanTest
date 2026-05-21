require('dotenv/config');

const http = require('http');
const { AsyncLocalStorage } = require('async_hooks');
const { AndroidAgent, AndroidDevice } = require('@midscene/android');
const { Agent } = require('@midscene/core/agent');
const {
  AbstractInterface,
  defineActionClearInput,
  defineActionDoubleClick,
  defineActionInput,
  defineActionLongPress,
  defineActionScroll,
  defineActionTap,
} = require('@midscene/core/device');

const PORT = Number(process.env.PORT || 8005);
const MODEL_ENV_KEYS = [
  'MIDSCENE_MODEL_NAME',
  'MIDSCENE_MODEL_BASE_URL',
  'MIDSCENE_MODEL_API_KEY',
  'MIDSCENE_MODEL_FAMILY',
];
const agentCache = new Map();
const IOS_AGENT_URL = (process.env.IOS_AGENT_URL || '').replace(/\/$/, '');
const warningCaptureStorage = new AsyncLocalStorage();
const originalConsoleWarn = console.warn.bind(console);

console.warn = (...args) => {
  const capturedWarnings = warningCaptureStorage.getStore();
  if (capturedWarnings) {
    capturedWarnings.push(args);
  }
  originalConsoleWarn(...args);
};

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

function cacheKey(platform, deviceId) {
  return `${platform || 'android'}:${deviceId}`;
}

function normalizePlatform(platform) {
  return String(platform || 'android').toLowerCase() === 'ios' ? 'ios' : 'android';
}

function requireIOSAgentUrl() {
  if (!IOS_AGENT_URL) {
    throw new Error('iOS Midscene AI requires IOS_AGENT_URL for midscene-runner.');
  }
}

function sanitizeMessage(value) {
  return String(value || '')
    .replace(/(api[_-]?key|authorization|token|cookie)(["':= ]+)[^"',\s]+/gi, '$1$2***')
    .trim();
}

async function readJsonResponse(response, fallbackMessage) {
  let data = {};
  try {
    data = await response.json();
  } catch (error) {
    // keep default object
  }
  if (!response.ok) {
    const detail = data.detail || data.error || fallbackMessage || `HTTP ${response.status}`;
    throw new Error(String(detail));
  }
  return data;
}

class IOSDevice extends AbstractInterface {
  constructor(deviceId, options = {}) {
    super();
    this.deviceId = deviceId;
    this.options = options;
    this.interfaceType = 'ios';
    this.cachedScreen = null;
  }

  describe() {
    return `iOS DeviceId: ${this.deviceId}`;
  }

  async request(path, options = {}) {
    requireIOSAgentUrl();
    let response;
    try {
      response = await fetch(`${IOS_AGENT_URL}/devices/${encodeURIComponent(this.deviceId)}${path}`, {
        ...options,
        headers: {
          'content-type': 'application/json',
          ...(options.headers || {}),
        },
      });
    } catch (error) {
      throw new Error(`iOS Agent request failed: ${error.message || error}`);
    }
    return readJsonResponse(response, `iOS Agent request failed: ${path}`);
  }

  async screenshotBase64() {
    const data = await this.request('/screenshot');
    if (data.screen?.width && data.screen?.height) {
      this.cachedScreen = {
        width: Number(data.screen.width),
        height: Number(data.screen.height),
      };
    }
    const format = data.format || 'png';
    if (!data.image) {
      throw new Error('iOS Agent returned an empty screenshot');
    }
    return `data:image/${format};base64,${data.image}`;
  }

  async size() {
    if (!this.cachedScreen) {
      await this.screenshotBase64();
    }
    return this.cachedScreen || { width: 390, height: 844 };
  }

  actionSpace() {
    return [
      defineActionTap(async (param) => {
        const element = param.locate;
        if (!element) {
          throw new Error('Element not found, cannot tap');
        }
        await this.tap(element.center[0], element.center[1]);
      }),
      defineActionDoubleClick(async (param) => {
        const element = param.locate;
        if (!element) {
          throw new Error('Element not found, cannot double tap');
        }
        await this.tap(element.center[0], element.center[1]);
        await new Promise((resolve) => setTimeout(resolve, 120));
        await this.tap(element.center[0], element.center[1]);
      }),
      defineActionInput(async (param) => {
        const element = param.locate;
        if (element) {
          await this.tap(element.center[0], element.center[1]);
        }
        if (param.mode !== 'typeOnly') {
          await this.clearText();
        }
        if (param.mode === 'clear' || !param.value) {
          return;
        }
        await this.text(String(param.value));
      }),
      defineActionClearInput(async (param) => {
        const element = param.locate;
        if (element) {
          await this.tap(element.center[0], element.center[1]);
        }
        await this.clearText();
      }),
      defineActionLongPress(async (param) => {
        const element = param.locate;
        if (!element) {
          throw new Error('LongPress requires an element to be located');
        }
        await this.longPress(element.center[0], element.center[1], param.duration);
      }),
      defineActionScroll(async (param) => {
        const size = await this.size();
        const element = param.locate;
        const center = element?.center || [size.width / 2, size.height / 2];
        const distance = Number(param.distance || Math.round(size.height * 0.45));
        const direction = param.direction || 'down';
        const point = this.scrollPoints(center, direction, distance, size);
        await this.swipe(point.startX, point.startY, point.endX, point.endY, 500);
      }),
    ];
  }

  scrollPoints(center, direction, distance, size) {
    const margin = 8;
    const clampX = (value) => Math.max(margin, Math.min(size.width - margin, Math.round(value)));
    const clampY = (value) => Math.max(margin, Math.min(size.height - margin, Math.round(value)));
    const x = clampX(center[0]);
    const y = clampY(center[1]);
    if (direction === 'up') {
      return { startX: x, startY: clampY(y - distance / 2), endX: x, endY: clampY(y + distance / 2) };
    }
    if (direction === 'left') {
      return { startX: clampX(x - distance / 2), startY: y, endX: clampX(x + distance / 2), endY: y };
    }
    if (direction === 'right') {
      return { startX: clampX(x + distance / 2), startY: y, endX: clampX(x - distance / 2), endY: y };
    }
    return { startX: x, startY: clampY(y + distance / 2), endX: x, endY: clampY(y - distance / 2) };
  }

  async tap(x, y) {
    return this.request('/tap', {
      method: 'POST',
      body: JSON.stringify({ x, y, includeScreen: false }),
    });
  }

  async swipe(startX, startY, endX, endY, durationMs = 500) {
    return this.request('/swipe', {
      method: 'POST',
      body: JSON.stringify({ startX, startY, endX, endY, durationMs, includeScreen: false }),
    });
  }

  async longPress(x, y, durationMs = 800) {
    return this.request('/long-press', {
      method: 'POST',
      body: JSON.stringify({ x, y, durationMs, includeScreen: false }),
    });
  }

  async text(text) {
    return this.request('/text', {
      method: 'POST',
      body: JSON.stringify({ text, includeScreen: false }),
    });
  }

  async clearText() {
    return this.request('/clear-text', {
      method: 'POST',
      body: JSON.stringify({ includeScreen: false }),
    });
  }

  async destroy() {
    if (!IOS_AGENT_URL) {
      return;
    }
    try {
      await this.request('/debug-session', {
        method: 'DELETE',
      });
    } catch (error) {
      console.warn(`Failed to release iOS debug session for ${this.deviceId}: ${error.message || error}`);
    }
  }
}

async function getAndroidAgent(deviceId) {
  const key = cacheKey('android', deviceId);
  const cached = agentCache.get(key);
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
  agentCache.set(key, entry);
  return agent;
}

async function getIOSAgent(deviceId) {
  const key = cacheKey('ios', deviceId);
  const cached = agentCache.get(key);
  if (cached) {
    return cached.agent;
  }

  const device = new IOSDevice(deviceId);
  const agent = new Agent(device, {
    generateReport: false,
    autoPrintReportMsg: false,
    cacheId: process.env.MIDSCENE_CACHE === 'true' ? `device-farm-ios-${deviceId}` : undefined,
    aiActContext: process.env.MIDSCENE_AI_ACT_CONTEXT || undefined,
  });

  const entry = { device, agent };
  agentCache.set(key, entry);
  return agent;
}

async function getAgent(platform, deviceId) {
  if (platform === 'ios') {
    return getIOSAgent(deviceId);
  }
  return getAndroidAgent(deviceId);
}

async function rebuildAgent(platform, deviceId) {
  await destroyAgent(platform, deviceId);
  return getAgent(platform, deviceId);
}

async function destroyAgent(platform, deviceId) {
  const key = cacheKey(platform, deviceId);
  const cached = agentCache.get(key);
  agentCache.delete(key);
  if (cached?.device && typeof cached.device.destroy === 'function') {
    try {
      await cached.device.destroy();
    } catch (error) {
      console.warn(`Failed to destroy ${platform} device for ${deviceId}: ${error.message}`);
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

function compactErrorMessage(error) {
  const message = error?.message || String(error);
  return sanitizeMessage(String(message).split('\n').find((line) => line.trim()) || String(message));
}

function summarizeErrorObject(error) {
  if (!error || typeof error !== 'object') {
    return '';
  }

  const nested = error.error && typeof error.error === 'object' ? error.error : {};
  const status = error.status || nested.status;
  const code = error.code || nested.code;
  const type = error.type || nested.type;
  const message = nested.message || error.message;
  const requestId = error.requestID || error.request_id || nested.requestID || nested.request_id;

  const parts = [];
  if (status) {
    parts.push(String(status));
  }
  if (code || type) {
    parts.push(String(code || type));
  }
  if (message) {
    parts.push(String(message));
  }
  if (requestId) {
    parts.push(`request_id=${requestId}`);
  }
  return sanitizeMessage(parts.join(' - '));
}

function summarizeWarningArgs(args) {
  const objectSummary = args
    .map((arg) => summarizeErrorObject(arg))
    .find(Boolean);
  if (objectSummary) {
    return objectSummary;
  }
  return sanitizeMessage(
    args
      .map((arg) => {
        if (arg instanceof Error) {
          return arg.message;
        }
        if (typeof arg === 'string') {
          return arg;
        }
        return '';
      })
      .filter(Boolean)
      .join(' '),
  );
}

function capturedModelErrorMessage(capturedWarnings) {
  for (let index = capturedWarnings.length - 1; index >= 0; index -= 1) {
    const args = capturedWarnings[index];
    const text = args.map((arg) => (typeof arg === 'string' ? arg : arg?.message || '')).join(' ');
    if (/call AI error|AI call failed|PermissionDenied|Quota|AllocationQuota|model/i.test(text)) {
      const summary = summarizeWarningArgs(args);
      if (summary) {
        return `Model request failed: ${summary}`;
      }
    }
  }
  return '';
}

function isGenericLocateError(message) {
  return /^failed to locate element:\s*$/i.test(String(message || '').trim());
}

function compactExecutionError(error, capturedWarnings = []) {
  const message = compactErrorMessage(error);
  const modelMessage = capturedModelErrorMessage(capturedWarnings);
  if (modelMessage && (isGenericLocateError(message) || /AI response|locate|assert|parse/i.test(message))) {
    return modelMessage;
  }
  return message;
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
        if (agent.interface?.interfaceType === 'ios') {
          throw new Error('iOS Midscene AI does not support ai_key yet. Use app.input_text() after focusing an input field, or use Appium directly.');
        }
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

  const {
    task_id: taskId,
    device_id: deviceId,
    operation,
    payload = {},
    timeout_ms: timeoutMs = 30000,
  } = body;
  const platform = normalizePlatform(body.platform);
  if (!taskId || !deviceId || !operation) {
    jsonResponse(res, 400, {
      success: false,
      error: 'task_id, device_id and operation are required',
    });
    return;
  }

  const capturedWarnings = [];
  try {
    requireModelConfig();
    let agent = await getAgent(platform, deviceId);
    let result;
    const abortController = new AbortController();
    const runWithTimeout = () => withTimeout(
      warningCaptureStorage.run(
        capturedWarnings,
        () => executeOperation(agent, operation, payload, timeoutMs, abortController.signal),
      ),
      timeoutMs,
      () => {
        abortController.abort();
        void destroyAgent(platform, deviceId);
      },
    );

    try {
      result = await runWithTimeout();
    } catch (error) {
      if (/device|adb|scrcpy|connect|closed|disconnect|wda|appium|session/i.test(error.message)) {
        agent = await rebuildAgent(platform, deviceId);
        result = await runWithTimeout();
      } else {
        throw error;
      }
    }

    jsonResponse(res, 200, {
      success: true,
      platform,
      operation,
      result: result ?? null,
      error: null,
      duration_ms: Date.now() - startedAt,
    });
  } catch (error) {
    const message = compactExecutionError(error, capturedWarnings);
    console.error(`[${taskId}] ${operation} failed on ${platform}:${deviceId}: ${message}`);
    jsonResponse(res, 500, {
      success: false,
      platform,
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
      ios_agent_configured: Boolean(IOS_AGENT_URL),
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
