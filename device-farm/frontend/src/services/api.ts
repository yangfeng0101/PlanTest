import axios from 'axios'
import type { Device, Script, ScriptRunSchedule, Task, TaskLogEntry, Report, PaginatedResponse, DeviceMetrics, MetricsAggregation, DeviceThresholdConfig, MetricAlert } from '@/types'

interface BackendListResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface DeviceListResponse {
  devices: Device[]
  total: number
}

export interface ScriptValidationResponse {
  valid: boolean
  errors: string[]
  warnings: string[]
}

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
  withCredentials: true, // Important: send cookies with requests
})

// Helper to get CSRF token from cookie
function getCsrfToken(): string | null {
  const match = document.cookie.match(/csrf_token=([^;]+)/)
  return match ? match[1] : null
}

// Add CSRF token to requests for state-changing methods
api.interceptors.request.use((config) => {
  const method = config.method?.toUpperCase() || ''
  const requiresCsrf = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)

  if (requiresCsrf) {
    const csrfToken = getCsrfToken()
    if (csrfToken) {
      config.headers['X-CSRF-Token'] = csrfToken
    }
  }

  return config
})

// Handle 401 responses - try to refresh token
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // If 401 and not already retrying
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      try {
        // Try to refresh tokens
        const response = await axios.post('/api/v1/auth/refresh', {}, {
          withCredentials: true,
        })

        if (response.status === 200) {
          // Update CSRF token for retry
          const newCsrfToken = getCsrfToken()
          if (newCsrfToken && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(originalRequest.method?.toUpperCase() || '')) {
            originalRequest.headers['X-CSRF-Token'] = newCsrfToken
          }
          return api(originalRequest)
        }
      } catch (refreshError) {
        // Refresh failed, redirect to login
        window.location.href = '/login'
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

// 设备 API
export const deviceApi = {
  // 获取设备列表
  getList: (params?: { status?: string; keyword?: string }) =>
    api.get<DeviceListResponse>('/devices', { params }),

  // 获取设备详情
  getDetail: (id: string) =>
    api.get<Device>(`/devices/${id}`),

  // 占用设备
  occupy: (id: string) =>
    api.post(`/devices/${id}/occupy`),

  // 释放设备
  release: (id: string) =>
    api.post(`/devices/${id}/release`),
}

// 脚本 API
export const scriptApi = {
  // 获取脚本列表
  getList: (params?: { search?: string }) =>
    api.get<BackendListResponse<Script>>('/scripts', { params }),

  // 获取脚本详情
  getDetail: (id: string) =>
    api.get<Script>(`/scripts/${id}`),

  // 创建脚本
  create: (data: Omit<Script, 'id' | 'created_at' | 'updated_at'>) =>
    api.post<Script>('/scripts', data),

  // 校验脚本
  validate: (content: string) =>
    api.post<ScriptValidationResponse>('/scripts/validate', { content }),

  // 更新脚本
  update: (id: string, data: Partial<Script>) =>
    api.put<Script>(`/scripts/${id}`, data),

  // 删除脚本
  delete: (id: string) =>
    api.delete(`/scripts/${id}`),
}

// 任务 API
export const taskApi = {
  // 获取任务列表
  getList: (params?: { status?: string; device_id?: string; script_id?: string; schedule_id?: string; page?: number; page_size?: number }) =>
    api.get<BackendListResponse<Task>>('/tasks', { params }),

  // 创建任务
  create: (data: {
    device_id: string
    script_id: string
    device_platform?: 'android' | 'ios'
    device_capabilities?: Record<string, unknown>
    parameters?: Record<string, unknown>
  }) =>
    api.post<Task>('/tasks', data),

  // 获取任务详情
  getDetail: (id: string) =>
    api.get<Task>(`/tasks/${id}`),

  // 获取任务日志
  getLogs: (id: string, params?: { limit?: number }) =>
    api.get<TaskLogEntry[]>(`/tasks/${id}/logs`, { params }),

  // 取消任务
  cancel: (id: string) =>
    api.delete(`/tasks/${id}`),
}

export const scheduleApi = {
  getScriptRuns: (params?: { page?: number; page_size?: number; script_id?: string; status?: string; search?: string }) =>
    api.get<BackendListResponse<ScriptRunSchedule>>('/schedules/script-runs', { params }),

  createScriptRun: (data: {
    name: string
    script_id: string
    device_id: string
    schedule_mode: 'once' | 'daily'
    run_at?: string
    time_of_day?: string
    timezone: string
    parameters?: Record<string, unknown>
    notification_enabled?: boolean
    feishu_webhook_url?: string
    enabled?: boolean
  }) =>
    api.post<ScriptRunSchedule>('/schedules/script-runs', data),

  updateScriptRun: (id: string, data: Partial<{
    name: string
    script_id: string
    device_id: string
    schedule_mode: 'once' | 'daily'
    run_at: string
    time_of_day: string
    timezone: string
    parameters: Record<string, unknown>
    notification_enabled: boolean
    feishu_webhook_url: string
  }>) =>
    api.put<ScriptRunSchedule>(`/schedules/script-runs/${id}`, data),

  enableScriptRun: (id: string, enabled: boolean) =>
    api.post<ScriptRunSchedule>(`/schedules/script-runs/${id}/enable`, { enabled }),

  deleteScriptRun: (id: string) =>
    api.delete(`/schedules/script-runs/${id}`),
}

// 报告 API
export const reportApi = {
  // 获取报告列表
  getList: (params?: { page?: number; pageSize?: number }) =>
    api.get<PaginatedResponse<Report>>('/reports', { params }),

  // 获取报告详情
  getDetail: (id: string) =>
    api.get<Report>(`/reports/${id}`),
}

// 指标 API
export const metricsApi = {
  // 获取所有设备当前指标
  getAll: () =>
    api.get<DeviceMetrics[]>('/metrics'),

  // 获取单个设备当前指标
  getDevice: (deviceId: string) =>
    api.get<DeviceMetrics>(`/metrics/${deviceId}`),

  // 获取设备历史指标
  getHistory: (deviceId: string, params?: { startTime?: string; endTime?: string; hours?: number }) =>
    api.get<DeviceMetrics[]>(`/metrics/${deviceId}/history`, { params }),

  // 获取设备指标聚合
  getAggregation: (deviceId: string, params?: { startTime?: string; endTime?: string; hours?: number }) =>
    api.get<MetricsAggregation>(`/metrics/${deviceId}/aggregation`, { params }),

  // 强制采集设备指标
  collectNow: (deviceId: string) =>
    api.post<DeviceMetrics>(`/metrics/${deviceId}/collect`),

  // 获取设备阈值配置
  getThresholds: (deviceId: string) =>
    api.get<DeviceThresholdConfig>(`/metrics/${deviceId}/thresholds`),

  // 更新设备阈值配置
  updateThresholds: (deviceId: string, config: Partial<DeviceThresholdConfig>) =>
    api.put<DeviceThresholdConfig>(`/metrics/${deviceId}/thresholds`, config),

  // 重置设备阈值配置
  resetThresholds: (deviceId: string) =>
    api.post<DeviceThresholdConfig>(`/metrics/${deviceId}/thresholds/reset`),

  // 获取设备指标告警
  getAlerts: (deviceId: string, limit?: number) =>
    api.get<MetricAlert[]>(`/metrics/${deviceId}/alerts`, { params: { limit } }),

  // 导出指标数据
  export: (params?: { deviceIds?: string[]; startTime?: string; endTime?: string; hours?: number; format?: 'json' | 'csv' }) =>
    api.post('/metrics/export', null, {
      params,
      responseType: 'blob',
    }),
}

export default api
