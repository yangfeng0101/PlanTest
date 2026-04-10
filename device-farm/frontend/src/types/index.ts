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

// 并行任务子任务
export interface SubTask {
  task_id: string
  device_id: string
  status: string
  created_at: string
  started_at?: string
  finished_at?: string
  result?: Record<string, unknown>
  error?: string
}

// 并行任务
export interface ParallelTask {
  id: string
  script_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'partial'
  selection_strategy: 'all' | 'random' | 'specific'
  max_concurrency: number
  parameters: Record<string, unknown>
  device_capabilities: Record<string, unknown>
  sub_tasks: SubTask[]
  total_devices: number
  completed_devices: number
  failed_devices: number
  created_at: string
  started_at?: string
  finished_at?: string
}

// 设备执行结果
export interface DeviceResult {
  device_id: string
  task_id: string
  status: string
  started_at?: string
  finished_at?: string
  duration: number
  total_tests: number
  passed_tests: number
  failed_tests: number
  skipped_tests: number
  success_rate: number
  error?: string
  logs: string[]
  screenshots: string[]
}

// 聚合结果
export interface AggregatedResult {
  id: string
  parallel_task_id: string
  script_id: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  started_at?: string
  finished_at?: string
  total_devices: number
  completed_devices: number
  failed_devices: number
  success_rate: number
  total_duration: number
  total_tests: number
  passed_tests: number
  failed_tests: number
  skipped_tests: number
  test_success_rate: number
  device_results: DeviceResult[]
  failed_device_ids: string[]
  created_at: string
}

// 并行报告摘要
export interface ParallelReportSummary {
  parallel_task_id: string
  script_id: string
  status: string
  total_devices: number
  completed_devices: number
  failed_devices: number
  device_success_rate: number
  total_tests: number
  passed_tests: number
  failed_tests: number
  skipped_tests: number
  test_success_rate: number
  total_duration: number
  avg_device_duration: number
  failed_device_ids: string[]
  failed_device_details: Array<{
    device_id: string
    status: string
    error?: string
    duration: number
  }>
  status_breakdown: Record<string, number>
}
