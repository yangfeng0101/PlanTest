const express = require('express');
const cors = require('cors');

const app = express();
const PORT = 3001;

app.use(cors());
app.use(express.json());

// 模拟设备数据
const devices = [
  {
    id: 'device-001',
    name: 'iPhone 15 Pro',
    model: 'A2848',
    brand: 'Apple',
    os: 'iOS',
    osVersion: '17.2',
    status: 'online',
    screenResolution: '2556x1179',
    screenSize: 6.1,
    cpu: 'A17 Pro',
    memory: '8GB',
    storage: '256GB',
    batteryLevel: 85,
    occupiedBy: null,
    occupiedAt: null,
    lastActiveAt: '2024-01-15 10:30:00',
    tags: ['iPhone', 'iOS17', '5G'],
  },
  {
    id: 'device-002',
    name: 'Samsung Galaxy S24 Ultra',
    model: 'SM-S928B',
    brand: 'Samsung',
    os: 'Android',
    osVersion: '14',
    status: 'busy',
    screenResolution: '3120x1440',
    screenSize: 6.8,
    cpu: 'Snapdragon 8 Gen 3',
    memory: '12GB',
    storage: '512GB',
    batteryLevel: 72,
    occupiedBy: 'user-001',
    occupiedAt: '2024-01-15 09:00:00',
    lastActiveAt: '2024-01-15 10:30:00',
    tags: ['Samsung', 'Android14', '5G'],
  },
  {
    id: 'device-003',
    name: 'Huawei Mate 60 Pro',
    model: 'ALN-AL00',
    brand: 'Huawei',
    os: 'HarmonyOS',
    osVersion: '4.0',
    status: 'online',
    screenResolution: '2720x1260',
    screenSize: 6.82,
    cpu: 'Kirin 9000S',
    memory: '12GB',
    storage: '512GB',
    batteryLevel: 95,
    occupiedBy: null,
    occupiedAt: null,
    lastActiveAt: '2024-01-15 10:25:00',
    tags: ['Huawei', 'HarmonyOS', '5G'],
  },
  {
    id: 'device-004',
    name: 'Google Pixel 8 Pro',
    model: 'GC3VE',
    brand: 'Google',
    os: 'Android',
    osVersion: '14',
    status: 'offline',
    screenResolution: '2992x1344',
    screenSize: 6.7,
    cpu: 'Tensor G3',
    memory: '12GB',
    storage: '256GB',
    batteryLevel: 0,
    occupiedBy: null,
    occupiedAt: null,
    lastActiveAt: '2024-01-14 18:00:00',
    tags: ['Pixel', 'Android14', 'Stock'],
  },
  {
    id: 'device-005',
    name: 'OnePlus 12',
    model: 'CPH2581',
    brand: 'OnePlus',
    os: 'Android',
    osVersion: '14',
    status: 'maintaining',
    screenResolution: '3168x1440',
    screenSize: 6.82,
    cpu: 'Snapdragon 8 Gen 3',
    memory: '16GB',
    storage: '512GB',
    batteryLevel: 60,
    occupiedBy: null,
    occupiedAt: null,
    lastActiveAt: '2024-01-15 08:00:00',
    tags: ['OnePlus', 'Android14', 'OxygenOS'],
  },
];

// 模拟脚本数据
const scripts = [
  {
    id: 'script-001',
    name: '登录流程测试',
    description: '测试用户登录功能，包括正常登录、异常登录等场景',
    language: 'python',
    content: `# 登录流程测试脚本
import time

def test_login_success():
    """测试正常登录"""
    print("测试正常登录...")
    # 模拟登录操作
    time.sleep(1)
    print("登录成功")

def test_login_invalid_password():
    """测试密码错误"""
    print("测试密码错误...")
    time.sleep(1)
    print("密码错误提示正确")

if __name__ == "__main__":
    test_login_success()
    test_login_invalid_password()`,
    createdAt: '2024-01-10 10:00:00',
    updatedAt: '2024-01-15 09:30:00',
    createdBy: 'user-001',
    tags: ['登录', '认证', '回归'],
  },
  {
    id: 'script-002',
    name: '支付流程测试',
    description: '测试完整支付流程，包括选择商品、支付、取消等',
    language: 'python',
    content: `# 支付流程测试脚本
import time

def test_payment_flow():
    """测试支付流程"""
    print("开始测试支付流程")
    # 选择商品
    print("选择商品...")
    time.sleep(0.5)
    # 确认订单
    print("确认订单...")
    time.sleep(0.5)
    # 完成支付
    print("完成支付...")
    time.sleep(0.5)
    print("支付流程测试完成")

if __name__ == "__main__":
    test_payment_flow()`,
    createdAt: '2024-01-12 14:00:00',
    updatedAt: '2024-01-14 16:20:00',
    createdBy: 'user-002',
    tags: ['支付', '订单', '集成测试'],
  },
  {
    id: 'script-003',
    name: '性能测试脚本',
    description: '测试应用启动时间和页面加载性能',
    language: 'javascript',
    content: `// 性能测试脚本
const startTime = Date.now();

function measureStartupTime() {
    console.log('测量应用启动时间...');
    const endTime = Date.now();
    const duration = endTime - startTime;
    console.log(\`启动耗时: \${duration}ms\`);
    return duration;
}

function measurePageLoad() {
    console.log('测量页面加载性能...');
    // 模拟页面加载
    setTimeout(() => {
        console.log('页面加载完成');
    }, 1000);
}

measureStartupTime();
measurePageLoad();`,
    createdAt: '2024-01-08 09:00:00',
    updatedAt: '2024-01-08 09:00:00',
    createdBy: 'user-001',
    tags: ['性能', '启动时间', '自动化'],
  },
];

// 模拟任务数据
const tasks = [
  {
    id: 'task-001',
    deviceId: 'device-001',
    deviceName: 'iPhone 15 Pro',
    scriptId: 'script-001',
    scriptName: '登录流程测试',
    status: 'success',
    createdAt: '2024-01-15 10:00:00',
    startedAt: '2024-01-15 10:01:00',
    finishedAt: '2024-01-15 10:03:00',
    duration: 120,
    result: '所有测试用例通过',
  },
  {
    id: 'task-002',
    deviceId: 'device-002',
    deviceName: 'Samsung Galaxy S24 Ultra',
    scriptId: 'script-002',
    scriptName: '支付流程测试',
    status: 'failed',
    createdAt: '2024-01-15 10:30:00',
    startedAt: '2024-01-15 10:31:00',
    finishedAt: '2024-01-15 10:34:00',
    duration: 180,
    result: '部分测试用例失败',
  },
];

// API 路由

// 设备列表
app.get('/api/v1/devices', (req, res) => {
  console.log('GET /api/v1/devices');
  res.json({ data: devices, total: devices.length });
});

// 设备详情
app.get('/api/v1/devices/:id', (req, res) => {
  const { id } = req.params;
  const device = devices.find((d) => d.id === id);
  if (device) {
    res.json(device);
  } else {
    res.status(404).json({ error: 'Device not found' });
  }
});

// 占用设备
app.post('/api/v1/devices/:id/occupy', (req, res) => {
  const { id } = req.params;
  const device = devices.find((d) => d.id === id);
  if (device) {
    if (device.status === 'online') {
      device.status = 'busy';
      device.occupiedBy = 'current-user';
      device.occupiedAt = new Date().toISOString();
      res.json({ success: true, message: '设备占用成功' });
    } else {
      res.status(400).json({ error: '设备不可用' });
    }
  } else {
    res.status(404).json({ error: 'Device not found' });
  }
});

// 释放设备
app.post('/api/v1/devices/:id/release', (req, res) => {
  const { id } = req.params;
  const device = devices.find((d) => d.id === id);
  if (device) {
    device.status = 'online';
    device.occupiedBy = null;
    device.occupiedAt = null;
    res.json({ success: true, message: '设备释放成功' });
  } else {
    res.status(404).json({ error: 'Device not found' });
  }
});

// 脚本列表
app.get('/api/v1/scripts', (req, res) => {
  console.log('GET /api/v1/scripts');
  res.json(scripts);
});

// 脚本详情
app.get('/api/v1/scripts/:id', (req, res) => {
  const { id } = req.params;
  const script = scripts.find((s) => s.id === id);
  if (script) {
    res.json(script);
  } else {
    res.status(404).json({ error: 'Script not found' });
  }
});

// 创建脚本
app.post('/api/v1/scripts', (req, res) => {
  const newScript = {
    id: `script-${Date.now()}`,
    ...req.body,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  scripts.push(newScript);
  res.json(newScript);
});

// 更新脚本
app.put('/api/v1/scripts/:id', (req, res) => {
  const { id } = req.params;
  const index = scripts.findIndex((s) => s.id === id);
  if (index !== -1) {
    scripts[index] = {
      ...scripts[index],
      ...req.body,
      updatedAt: new Date().toISOString(),
    };
    res.json(scripts[index]);
  } else {
    res.status(404).json({ error: 'Script not found' });
  }
});

// 删除脚本
app.delete('/api/v1/scripts/:id', (req, res) => {
  const { id } = req.params;
  const index = scripts.findIndex((s) => s.id === id);
  if (index !== -1) {
    scripts.splice(index, 1);
    res.json({ success: true });
  } else {
    res.status(404).json({ error: 'Script not found' });
  }
});

// 任务列表
app.get('/api/v1/tasks', (req, res) => {
  console.log('GET /api/v1/tasks');
  res.json(tasks);
});

// 创建任务
app.post('/api/v1/tasks', (req, res) => {
  const { deviceId, scriptId } = req.body;
  const device = devices.find((d) => d.id === deviceId);
  const script = scripts.find((s) => s.id === scriptId);

  if (!device || !script) {
    return res.status(400).json({ error: 'Invalid device or script' });
  }

  const newTask = {
    id: `task-${Date.now()}`,
    deviceId,
    deviceName: device.name,
    scriptId,
    scriptName: script.name,
    status: 'pending',
    createdAt: new Date().toISOString(),
  };

  tasks.push(newTask);
  res.json(newTask);
});

// 报告列表
app.get('/api/v1/reports', (req, res) => {
  console.log('GET /api/v1/reports');
  const reports = tasks
    .filter((t) => t.status === 'success' || t.status === 'failed')
    .map((t) => ({
      id: `report-${t.id}`,
      taskId: t.id,
      deviceName: t.deviceName,
      scriptName: t.scriptName,
      status: t.status,
      summary: {
        total: t.status === 'success' ? 10 : 8,
        passed: t.status === 'success' ? 10 : 6,
        failed: t.status === 'success' ? 0 : 2,
        skipped: 0,
      },
      duration: t.duration,
      createdAt: t.finishedAt || t.createdAt,
      logs: t.result,
      screenshots: [],
    }));

  res.json({ data: reports, total: reports.length });
});

// 启动服务器
app.listen(PORT, () => {
  console.log(`Mock API server running at http://localhost:${PORT}`);
  console.log('Available endpoints:');
  console.log('  GET    /api/v1/devices');
  console.log('  GET    /api/v1/devices/:id');
  console.log('  POST   /api/v1/devices/:id/occupy');
  console.log('  POST   /api/v1/devices/:id/release');
  console.log('  GET    /api/v1/scripts');
  console.log('  POST   /api/v1/scripts');
  console.log('  GET    /api/v1/tasks');
  console.log('  POST   /api/v1/tasks');
  console.log('  GET    /api/v1/reports');
});
