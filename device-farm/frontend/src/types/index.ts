// 设备类型
export interface DeviceDrivers {
  metrics: string
  screen: string
  uiHierarchy: string
  control: string
}

export interface DeviceCapabilities {
  screenMirror: boolean
  remoteControl: boolean
  uiHierarchy: boolean
  metrics: boolean
  screenshot: boolean
  appManagement: boolean
}

export interface Device {
  id: string
  name: string
  model: string
  brand: string
  os: string
  osVersion: string
  displayOs: string
  displayOsVersion: string
  connectionType: string
  drivers: DeviceDrivers
  capabilities: DeviceCapabilities
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

// 设备指标
export interface DeviceMetrics {
  device_id: string
  timestamp: string
  cpu_usage: number
  cpu_cores?: number
  memory_usage: number
  memory_total_mb?: number
  memory_used_mb?: number
  memory_free_mb?: number
  network_rx_bytes: number
  network_tx_bytes: number
  network_rx_speed_kbps: number
  network_tx_speed_kbps: number
  battery_level: number
  battery_status: string
  battery_temperature?: number
  cpu_temperature?: number
  device_temperature?: number
  uptime_seconds?: number
}

// 指标聚合
export interface MetricsAggregation {
  device_id: string
  start_time: string
  end_time: string
  cpu_usage_avg?: number
  cpu_usage_max?: number
  cpu_usage_min?: number
  memory_usage_avg?: number
  memory_usage_max?: number
  memory_usage_min?: number
  network_rx_total_mb?: number
  network_tx_total_mb?: number
  network_rx_avg_kbps?: number
  network_tx_avg_kbps?: number
  battery_level_avg?: number
  battery_level_min?: number
  temperature_avg?: number
  temperature_max?: number
  sample_count: number
}

// 设备指标阈值配置
export interface DeviceThresholdConfig {
  device_id: string
  cpu_warning: number
  cpu_critical: number
  memory_warning: number
  memory_critical: number
  battery_warning: number
  battery_critical: number
  temperature_warning: number
  temperature_critical: number
}

// 指标告警
export interface MetricAlert {
  id: string
  device_id: string
  metric_type: string
  severity: 'warning' | 'critical'
  value: number
  threshold: number
  timestamp: string
  acknowledged: boolean
}

// 脚本类型
export interface Script {
  id: string
  name: string
  description: string
  script_type: 'python' | 'javascript'
  content: string
  created_at: string
  updated_at: string
  created_by?: string
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
  task_id: string
  title?: string
  description?: string
  status: 'pending' | 'generating' | 'completed' | 'failed'
  format: 'html' | 'pdf' | 'json' | 'markdown'
  created_at: string
  updated_at: string
  file_size?: number
  detail?: {
    summary: {
      total: number
      passed: number
      failed: number
      skipped: number
      duration: number
      success_rate: number
    }
  }
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
