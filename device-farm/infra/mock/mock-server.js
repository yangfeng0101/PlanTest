const express = require('express');
const cors = require('cors');
const app = express();
const PORT = process.env.PORT || 3000;

// 中间件
app.use(cors());
app.use(express.json());

// 请求日志
app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
  next();
});

// ==================== 模拟数据 ====================
const devices = [
  {
    id: 'device-001',
    serial: 'ABC123456789',
    platform: 'android',
    model: 'Pixel 6',
    brand: 'Google',
    osVersion: '13',
    screenWidth: 1080,
    screenHeight: 2400,
    status: 'online',
    ownerId: null,
    createdAt: '2024-01-15T08:00:00Z',
    updatedAt: '2024-01-20T10:30:00Z'
  },
  {
    id: 'device-002',
    serial: 'DEF987654321',
    platform: 'android',
    model: 'Galaxy S22',
    brand: 'Samsung',
    osVersion: '13',
    screenWidth: 1080,
    screenHeight: 2340,
    status: 'online',
    ownerId: null,
    createdAt: '2024-01-16T09:00:00Z',
    updatedAt: '2024-01-20T11:00:00Z'
  },
  {
    id: 'device-003',
    serial: 'GHI456789123',
    platform: 'ios',
    model: 'iPhone 14 Pro',
    brand: 'Apple',
    osVersion: '16.0',
    screenWidth: 1179,
    screenHeight: 2556,
    status: 'offline',
    ownerId: null,
    createdAt: '2024-01-17T10:00:00Z',
    updatedAt: '2024-01-19T15:00:00Z'
  },
  {
    id: 'device-004',
    serial: 'JKL789123456',
    platform: 'ios',
    model: 'iPhone 13',
    brand: 'Apple',
    osVersion: '15.5',
    screenWidth: 1170,
    screenHeight: 2532,
    status: 'busy',
    ownerId: 'user-002',
    createdAt: '2024-01-18T11:00:00Z',
    updatedAt: '2024-01-20T14:00:00Z'
  },
  {
    id: 'device-005',
    serial: 'MNO123456789',
    platform: 'android',
    model: 'OnePlus 11',
    brand: 'OnePlus',
    osVersion: '13',
    screenWidth: 1440,
    screenHeight: 3216,
    status: 'maintenance',
    ownerId: null,
    createdAt: '2024-01-19T12:00:00Z',
    updatedAt: '2024-01-20T09:00:00Z'
  }
];

const scripts = [
  {
    id: 'script-001',
    name: 'Login Test',
    language: 'python',
    content: `# Login Test Script
import time

def test_login(driver):
    # 打开登录页面
    driver.get("https://example.com/login")

    # 输入用户名密码
    driver.find_element_by_id("username").send_keys("testuser")
    driver.find_element_by_id("password").send_keys("password123")

    # 点击登录
    driver.find_element_by_id("login-btn").click()

    # 验证登录成功
    time.sleep(2)
    assert "Dashboard" in driver.title

if __name__ == "__main__":
    test_login(driver)`,
    version: 1,
    description: 'Test user login flow',
    createdBy: 'user-001',
    createdAt: '2024-01-15T08:00:00Z',
    updatedAt: '2024-01-15T08:00:00Z'
  },
  {
    id: 'script-002',
    name: 'Purchase Flow',
    language: 'javascript',
    content: `// Purchase Flow Test
const { test, expect } = require('@playwright/test');

test('purchase flow', async ({ page }) => {
  await page.goto('https://example.com');

  // 添加商品到购物车
  await page.click('[data-testid="add-to-cart"]');

  // 进入购物车
  await page.click('[data-testid="cart-icon"]');

  // 确认订单
  await page.click('[data-testid="checkout-btn"]');

  // 验证订单成功
  await expect(page.locator('.success-message')).toBeVisible();
});`,
    version: 2,
    description: 'Test purchase process',
    createdBy: 'user-001',
    createdAt: '2024-01-16T09:00:00Z',
    updatedAt: '2024-01-18T14:00:00Z'
  },
  {
    id: 'script-003',
    name: 'Appium iOS Test',
    language: 'appium',
    content: `# Appium iOS Test
from appium import webdriver

desired_caps = {
    'platformName': 'iOS',
    'platformVersion': '16.0',
    'deviceName': 'iPhone 14',
    'app': '/path/to/app.app'
}

driver = webdriver.Remote('http://localhost:4723/wd/hub', desired_caps)

def test_ios_app():
    # 测试代码
    pass`,
    version: 1,
    description: 'Appium test for iOS app',
    createdBy: 'user-002',
    createdAt: '2024-01-17T10:00:00Z',
    updatedAt: '2024-01-17T10:00:00Z'
  }
];

const tasks = [
  {
    id: 'task-001',
    name: 'Login Test - Pixel 6',
    scriptId: 'script-001',
    deviceId: 'device-001',
    status: 'completed',
    priority: 0,
    params: { timeout: 30 },
    startedAt: '2024-01-20T10:00:00Z',
    finishedAt: '2024-01-20T10:01:30Z',
    createdBy: 'user-002',
    createdAt: '2024-01-20T09:55:00Z'
  },
  {
    id: 'task-002',
    name: 'Purchase Flow - Galaxy S22',
    scriptId: 'script-002',
    deviceId: 'device-002',
    status: 'running',
    priority: 1,
    params: { timeout: 60 },
    startedAt: '2024-01-20T14:00:00Z',
    finishedAt: null,
    createdBy: 'user-002',
    createdAt: '2024-01-20T13:55:00Z'
  },
  {
    id: 'task-003',
    name: 'Login Test - iPhone 13',
    scriptId: 'script-001',
    deviceId: 'device-004',
    status: 'pending',
    priority: 0,
    params: {},
    startedAt: null,
    finishedAt: null,
    createdBy: 'user-001',
    createdAt: '2024-01-20T15:00:00Z'
  },
  {
    id: 'task-004',
    name: 'iOS App Test',
    scriptId: 'script-003',
    deviceId: 'device-003',
    status: 'failed',
    priority: 2,
    params: { timeout: 120 },
    startedAt: '2024-01-19T14:00:00Z',
    finishedAt: '2024-01-19T14:05:00Z',
    createdBy: 'user-001',
    createdAt: '2024-01-19T13:50:00Z'
  }
];

const reports = [
  {
    id: 'report-001',
    taskId: 'task-001',
    totalCases: 10,
    passedCases: 8,
    failedCases: 2,
    skippedCases: 0,
    duration: 90,
    videoUrl: 'https://minio.example.com/videos/task-001.mp4',
    logUrl: 'https://minio.example.com/logs/task-001.log',
    reportUrl: 'https://minio.example.com/reports/task-001.html',
    summary: 'Most tests passed, 2 failures in edge cases',
    createdAt: '2024-01-20T10:01:30Z'
  },
  {
    id: 'report-002',
    taskId: 'task-004',
    totalCases: 5,
    passedCases: 2,
    failedCases: 3,
    skippedCases: 0,
    duration: 300,
    videoUrl: 'https://minio.example.com/videos/task-004.mp4',
    logUrl: 'https://minio.example.com/logs/task-004.log',
    reportUrl: 'https://minio.example.com/reports/task-004.html',
    summary: 'Multiple failures due to device offline',
    createdAt: '2024-01-19T14:05:00Z'
  }
];

const caseResults = {
  'report-001': [
    { id: 'case-001', reportId: 'report-001', caseName: 'test_login_valid', status: 'passed', duration: 1200, errorMessage: null, stackTrace: null },
    { id: 'case-002', reportId: 'report-001', caseName: 'test_login_invalid_password', status: 'passed', duration: 800, errorMessage: null, stackTrace: null },
    { id: 'case-003', reportId: 'report-001', caseName: 'test_login_empty_fields', status: 'passed', duration: 500, errorMessage: null, stackTrace: null },
    { id: 'case-004', reportId: 'report-001', caseName: 'test_logout', status: 'passed', duration: 600, errorMessage: null, stackTrace: null },
    { id: 'case-005', reportId: 'report-001', caseName: 'test_session_timeout', status: 'failed', duration: 3000, errorMessage: 'Timeout exceeded', stackTrace: 'Error: Timeout...\n  at Test.run()' },
    { id: 'case-006', reportId: 'report-001', caseName: 'test_remember_me', status: 'passed', duration: 900, errorMessage: null, stackTrace: null },
    { id: 'case-007', reportId: 'report-001', caseName: 'test_password_reset', status: 'passed', duration: 1500, errorMessage: null, stackTrace: null },
    { id: 'case-008', reportId: 'report-001', caseName: 'test_social_login', status: 'passed', duration: 2000, errorMessage: null, stackTrace: null },
    { id: 'case-009', reportId: 'report-001', caseName: 'test_two_factor_auth', status: 'failed', duration: 5000, errorMessage: '2FA code not received', stackTrace: 'Error: 2FA timeout...' },
    { id: 'case-010', reportId: 'report-001', caseName: 'test_account_lockout', status: 'passed', duration: 1000, errorMessage: null, stackTrace: null }
  ]
};

const screenSessions = {};

// ==================== 工具函数 ====================
function successResponse(data, message = 'Success') {
  return { code: 0, message, data };
}

function errorResponse(code, message, errors = null) {
  const response = { code, message };
  if (errors) response.errors = errors;
  return response;
}

function paginate(array, page, pageSize) {
  const start = (page - 1) * pageSize;
  const end = start + pageSize;
  return {
    total: array.length,
    page,
    pageSize,
    items: array.slice(start, end)
  };
}

// ==================== 设备管理 API ====================

// 获取设备列表
app.get('/api/v1/devices', (req, res) => {
  const { status, platform, page = 1, pageSize = 20 } = req.query;

  let filtered = [...devices];

  if (status) {
    filtered = filtered.filter(d => d.status === status);
  }
  if (platform) {
    filtered = filtered.filter(d => d.platform === platform);
  }

  res.json(successResponse(paginate(filtered, parseInt(page), parseInt(pageSize))));
});

// 获取设备详情
app.get('/api/v1/devices/:deviceId', (req, res) => {
  const device = devices.find(d => d.id === req.params.deviceId);

  if (!device) {
    return res.status(404).json(errorResponse(404, 'Device not found'));
  }

  res.json(successResponse(device));
});

// 注册设备
app.post('/api/v1/devices', (req, res) => {
  const { serial, platform, model, brand, osVersion, screenWidth, screenHeight } = req.body;

  if (!serial || !platform) {
    return res.status(400).json(errorResponse(400, 'Missing required fields'));
  }

  if (devices.some(d => d.serial === serial)) {
    return res.status(409).json(errorResponse(409, 'Device serial already exists'));
  }

  const newDevice = {
    id: `device-${String(devices.length + 1).padStart(3, '0')}`,
    serial,
    platform,
    model: model || null,
    brand: brand || null,
    osVersion: osVersion || null,
    screenWidth: screenWidth || null,
    screenHeight: screenHeight || null,
    status: 'offline',
    ownerId: null,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };

  devices.push(newDevice);
  res.status(201).json(successResponse(newDevice, 'Device registered successfully'));
});

// 更新设备
app.put('/api/v1/devices/:deviceId', (req, res) => {
  const device = devices.find(d => d.id === req.params.deviceId);

  if (!device) {
    return res.status(404).json(errorResponse(404, 'Device not found'));
  }

  const { model, brand, osVersion, status } = req.body;

  if (model) device.model = model;
  if (brand) device.brand = brand;
  if (osVersion) device.osVersion = osVersion;
  if (status) device.status = status;
  device.updatedAt = new Date().toISOString();

  res.json(successResponse(device, 'Device updated successfully'));
});

// 删除设备
app.delete('/api/v1/devices/:deviceId', (req, res) => {
  const index = devices.findIndex(d => d.id === req.params.deviceId);

  if (index === -1) {
    return res.status(404).json(errorResponse(404, 'Device not found'));
  }

  devices.splice(index, 1);
  res.status(204).send();
});

// 占用设备
app.post('/api/v1/devices/:deviceId/acquire', (req, res) => {
  const device = devices.find(d => d.id === req.params.deviceId);

  if (!device) {
    return res.status(404).json(errorResponse(404, 'Device not found'));
  }

  if (device.status !== 'online') {
    return res.status(409).json(errorResponse(409, `Device is ${device.status}`));
  }

  const { userId, reason } = req.body;
  device.status = 'busy';
  device.ownerId = userId || 'user-current';
  device.updatedAt = new Date().toISOString();

  res.json(successResponse(device, 'Device acquired successfully'));
});

// 释放设备
app.post('/api/v1/devices/:deviceId/release', (req, res) => {
  const device = devices.find(d => d.id === req.params.deviceId);

  if (!device) {
    return res.status(404).json(errorResponse(404, 'Device not found'));
  }

  device.status = 'online';
  device.ownerId = null;
  device.updatedAt = new Date().toISOString();

  res.json(successResponse(device, 'Device released successfully'));
});

// ==================== 投屏控制 API ====================

// 创建投屏会话
app.post('/api/v1/devices/:deviceId/screen/session', (req, res) => {
  const device = devices.find(d => d.id === req.params.deviceId);

  if (!device) {
    return res.status(404).json(errorResponse(404, 'Device not found'));
  }

  if (screenSessions[req.params.deviceId]) {
    return res.status(409).json(errorResponse(409, 'Active session already exists'));
  }

  const sessionId = `session-${Date.now()}`;
  const session = {
    sessionId,
    deviceId: req.params.deviceId,
    webrtcOffer: 'v=0\r\no=- 123456789 123456789 IN IP4 127.0.0.1\r\n...',
    iceServers: [
      { urls: ['stun:stun.l.google.com:19302'] }
    ],
    startedAt: new Date().toISOString()
  };

  screenSessions[req.params.deviceId] = session;
  res.json(successResponse(session, 'Session created successfully'));
});

// 获取投屏会话
app.get('/api/v1/devices/:deviceId/screen/session', (req, res) => {
  const session = screenSessions[req.params.deviceId];

  if (!session) {
    return res.status(404).json(errorResponse(404, 'No active session'));
  }

  res.json(successResponse(session));
});

// 关闭投屏会话
app.delete('/api/v1/devices/:deviceId/screen/session', (req, res) => {
  if (!screenSessions[req.params.deviceId]) {
    return res.status(404).json(errorResponse(404, 'No active session'));
  }

  delete screenSessions[req.params.deviceId];
  res.status(204).send();
});

// 发送输入事件
app.post('/api/v1/devices/:deviceId/screen/input', (req, res) => {
  const device = devices.find(d => d.id === req.params.deviceId);

  if (!device) {
    return res.status(404).json(errorResponse(404, 'Device not found'));
  }

  const { type, x, y, startX, startY, endX, endY, duration, keyCode, text } = req.body;

  // 模拟处理输入事件
  console.log(`Input event on ${device.model}:`, req.body);

  res.json(successResponse({ processed: true }, 'Input event sent'));
});

// ==================== 脚本管理 API ====================

// 获取脚本列表
app.get('/api/v1/scripts', (req, res) => {
  const { language, page = 1, pageSize = 20 } = req.query;

  let filtered = [...scripts];

  if (language) {
    filtered = filtered.filter(s => s.language === language);
  }

  res.json(successResponse(paginate(filtered, parseInt(page), parseInt(pageSize))));
});

// 获取脚本详情
app.get('/api/v1/scripts/:scriptId', (req, res) => {
  const script = scripts.find(s => s.id === req.params.scriptId);

  if (!script) {
    return res.status(404).json(errorResponse(404, 'Script not found'));
  }

  res.json(successResponse(script));
});

// 创建脚本
app.post('/api/v1/scripts', (req, res) => {
  const { name, language, content, description } = req.body;

  if (!name || !language) {
    return res.status(400).json(errorResponse(400, 'Missing required fields'));
  }

  const newScript = {
    id: `script-${String(scripts.length + 1).padStart(3, '0')}`,
    name,
    language,
    content: content || '',
    version: 1,
    description: description || null,
    createdBy: 'user-current',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };

  scripts.push(newScript);
  res.status(201).json(successResponse(newScript, 'Script created successfully'));
});

// 更新脚本
app.put('/api/v1/scripts/:scriptId', (req, res) => {
  const script = scripts.find(s => s.id === req.params.scriptId);

  if (!script) {
    return res.status(404).json(errorResponse(404, 'Script not found'));
  }

  const { name, content, description } = req.body;

  if (name) script.name = name;
  if (content !== undefined) script.content = content;
  if (description !== undefined) script.description = description;
  script.version += 1;
  script.updatedAt = new Date().toISOString();

  res.json(successResponse(script, 'Script updated successfully'));
});

// 删除脚本
app.delete('/api/v1/scripts/:scriptId', (req, res) => {
  const index = scripts.findIndex(s => s.id === req.params.scriptId);

  if (index === -1) {
    return res.status(404).json(errorResponse(404, 'Script not found'));
  }

  scripts.splice(index, 1);
  res.status(204).send();
});

// ==================== 测试任务 API ====================

// 获取任务列表
app.get('/api/v1/tasks', (req, res) => {
  const { status, deviceId, page = 1, pageSize = 20 } = req.query;

  let filtered = [...tasks];

  if (status) {
    filtered = filtered.filter(t => t.status === status);
  }
  if (deviceId) {
    filtered = filtered.filter(t => t.deviceId === deviceId);
  }

  res.json(successResponse(paginate(filtered, parseInt(page), parseInt(pageSize))));
});

// 获取任务详情
app.get('/api/v1/tasks/:taskId', (req, res) => {
  const task = tasks.find(t => t.id === req.params.taskId);

  if (!task) {
    return res.status(404).json(errorResponse(404, 'Task not found'));
  }

  res.json(successResponse(task));
});

// 创建任务
app.post('/api/v1/tasks', (req, res) => {
  const { name, scriptId, deviceId, priority, params } = req.body;

  if (!name || !scriptId || !deviceId) {
    return res.status(400).json(errorResponse(400, 'Missing required fields'));
  }

  const device = devices.find(d => d.id === deviceId);
  if (!device || device.status !== 'online') {
    return res.status(409).json(errorResponse(409, 'Device not available'));
  }

  const newTask = {
    id: `task-${String(tasks.length + 1).padStart(3, '0')}`,
    name,
    scriptId,
    deviceId,
    status: 'pending',
    priority: priority || 0,
    params: params || {},
    startedAt: null,
    finishedAt: null,
    createdBy: 'user-current',
    createdAt: new Date().toISOString()
  };

  tasks.push(newTask);
  res.status(201).json(successResponse(newTask, 'Task created successfully'));
});

// 取消任务
app.delete('/api/v1/tasks/:taskId', (req, res) => {
  const task = tasks.find(t => t.id === req.params.taskId);

  if (!task) {
    return res.status(404).json(errorResponse(404, 'Task not found'));
  }

  if (task.status === 'running') {
    task.status = 'cancelled';
    task.finishedAt = new Date().toISOString();
  } else {
    task.status = 'cancelled';
  }

  res.json(successResponse(task, 'Task cancelled'));
});

// 执行任务
app.post('/api/v1/tasks/:taskId/run', (req, res) => {
  const task = tasks.find(t => t.id === req.params.taskId);

  if (!task) {
    return res.status(404).json(errorResponse(404, 'Task not found'));
  }

  if (task.status === 'running') {
    return res.status(409).json(errorResponse(409, 'Task is already running'));
  }

  const device = devices.find(d => d.id === task.deviceId);
  if (!device || device.status !== 'online') {
    return res.status(409).json(errorResponse(409, 'Device not available'));
  }

  task.status = 'running';
  task.startedAt = new Date().toISOString();

  res.json(successResponse(task, 'Task started'));
});

// ==================== 测试报告 API ====================

// 获取报告列表
app.get('/api/v1/reports', (req, res) => {
  const { taskId, page = 1, pageSize = 20 } = req.query;

  let filtered = [...reports];

  if (taskId) {
    filtered = filtered.filter(r => r.taskId === taskId);
  }

  res.json(successResponse(paginate(filtered, parseInt(page), parseInt(pageSize))));
});

// 获取报告详情
app.get('/api/v1/reports/:reportId', (req, res) => {
  const report = reports.find(r => r.id === req.params.reportId);

  if (!report) {
    return res.status(404).json(errorResponse(404, 'Report not found'));
  }

  const caseResultList = caseResults[report.id] || [];

  res.json(successResponse({
    report,
    caseResults: caseResultList
  }));
});

// ==================== 健康检查 ====================
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// ==================== 启动服务器 ====================
app.listen(PORT, () => {
  console.log(`
╔════════════════════════════════════════════╗
║   Device Farm Mock Server                  ║
║   Port: ${PORT}                              ║
║   Status: Running                           ║
╚════════════════════════════════════════════╝

Available Endpoints:
  - GET    /api/v1/devices
  - POST   /api/v1/devices
  - GET    /api/v1/devices/:id
  - PUT    /api/v1/devices/:id
  - DELETE /api/v1/devices/:id
  - POST   /api/v1/devices/:id/acquire
  - POST   /api/v1/devices/:id/release
  - POST   /api/v1/devices/:id/screen/session
  - GET    /api/v1/devices/:id/screen/session
  - DELETE /api/v1/devices/:id/screen/session
  - POST   /api/v1/devices/:id/screen/input
  - GET    /api/v1/scripts
  - POST   /api/v1/scripts
  - GET    /api/v1/scripts/:id
  - PUT    /api/v1/scripts/:id
  - DELETE /api/v1/scripts/:id
  - GET    /api/v1/tasks
  - POST   /api/v1/tasks
  - GET    /api/v1/tasks/:id
  - DELETE /api/v1/tasks/:id
  - POST   /api/v1/tasks/:id/run
  - GET    /api/v1/reports
  - GET    /api/v1/reports/:id
  `);
});
