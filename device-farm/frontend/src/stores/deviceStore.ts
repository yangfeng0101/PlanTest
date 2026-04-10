import { create } from 'zustand'
import type { Device } from '@/types'

interface DeviceState {
  devices: Device[]
  currentDevice: Device | null
  loading: boolean
  viewMode: 'card' | 'list'
  fetchDevices: () => Promise<void>
  setCurrentDevice: (device: Device | null) => void
  setViewMode: (mode: 'card' | 'list') => void
  occupyDevice: (id: string) => Promise<void>
  releaseDevice: (id: string) => Promise<void>
}

export const useDeviceStore = create<DeviceState>((set, get) => ({
  devices: [],
  currentDevice: null,
  loading: false,
  viewMode: 'card',

  fetchDevices: async () => {
    set({ loading: true })
    try {
      const { data } = await fetch('/api/v1/devices').then((res) => res.json())
      set({ devices: data || [], loading: false })
    } catch (error) {
      console.error('Failed to fetch devices:', error)
      set({ loading: false })
    }
  },

  setCurrentDevice: (device) => set({ currentDevice: device }),

  setViewMode: (mode) => set({ viewMode: mode }),

  occupyDevice: async (id) => {
    try {
      await fetch(`/api/v1/devices/${id}/occupy`, { method: 'POST' })
      const { fetchDevices } = get()
      await fetchDevices()
    } catch (error) {
      console.error('Failed to occupy device:', error)
    }
  },

  releaseDevice: async (id) => {
    try {
      await fetch(`/api/v1/devices/${id}/release`, { method: 'POST' })
      const { fetchDevices } = get()
      await fetchDevices()
    } catch (error) {
      console.error('Failed to release device:', error)
    }
  },
}))
