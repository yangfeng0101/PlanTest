import axios from 'axios'
import type { Device, Script, Task, Report, PaginatedResponse } from '@/types'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
})

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
