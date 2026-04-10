// 设备类型
export interface Device {
  id: string
  name: string
  model: string
  brand: string
  os: string
  osVersion: string
  status: 'online' | 'offline' | 'busy' | 'maintaining'
  screenResolution: string
  screenSize: number
  cpu: string
  memory: string
  storage: string
  batteryLevel: number
  occupiedBy?: string
  occupiedAt?: string
  lastActiveAt: string
  tags: string[]
  thumbnail?: string
}

// 脚本类型
export interface Script {
  id: string
  name: string
  description: string
  language: 'python' | 'javascript' | 'shell'
  content: string
  createdAt: string
  updatedAt: string
  createdBy: string
  tags: string[]
}

// 任务类型
export interface Task {
  id: string
  deviceId: string
  deviceName: string
  scriptId: string
  scriptName: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
  createdAt: string
  startedAt?: string
  finishedAt?: string
  duration?: number
  result?: string
}

// 报告类型
export interface Report {
  id: string
  taskId: string
  deviceName: string
  scriptName: string
  status: 'success' | 'failed'
  summary: {
    total: number
    passed: number
    failed: number
    skipped: number
  }
  duration: number
  createdAt: string
  logs: string
  screenshots: string[]
}

// 分页响应
export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  pageSize: number
}
