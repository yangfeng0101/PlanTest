import axios from 'axios'
import type { Device, Script, Task, Report, PaginatedResponse } from '@/types'

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
    api.get<Device[]>('/devices', { params }),

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
  getList: (params?: { keyword?: string }) =>
    api.get<Script[]>('/scripts', { params }),

  // 获取脚本详情
  getDetail: (id: string) =>
    api.get<Script>(`/scripts/${id}`),

  // 创建脚本
  create: (data: Omit<Script, 'id' | 'createdAt' | 'updatedAt'>) =>
    api.post<Script>('/scripts', data),

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
  getList: (params?: { status?: string; deviceId?: string }) =>
    api.get<Task[]>('/tasks', { params }),

  // 创建任务
  create: (data: { deviceId: string; scriptId: string }) =>
    api.post<Task>('/tasks', data),

  // 取消任务
  cancel: (id: string) =>
    api.post(`/tasks/${id}/cancel`),
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

export default api
