import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { message } from 'antd'
import type { Device } from '@/types'
import { mapDevice } from '@/utils/device'
import { fetchDeviceScreenInfo, fetchDevicesPayload } from './api'

export default function useScreenDevices() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const deviceIdFromUrl = searchParams.get('deviceId')
  const missingDeviceMessageShownRef = useRef(false)

  const [devices, setDevices] = useState<Device[]>([])
  const [devicesLoaded, setDevicesLoaded] = useState(false)
  const [selectedDevice, setSelectedDevice] = useState<string>(deviceIdFromUrl || '')
  const [deviceInfo, setDeviceInfo] = useState<{ width: number; height: number } | null>(null)

  const currentDevice = useMemo(
    () => devices.find((device) => device.id === selectedDevice),
    [devices, selectedDevice],
  )

  useEffect(() => {
    if (deviceIdFromUrl) {
      setSelectedDevice(deviceIdFromUrl)
      return
    }

    if (!missingDeviceMessageShownRef.current) {
      missingDeviceMessageShownRef.current = true
      message.warning('请先选择设备')
    }
    navigate('/devices', { replace: true })
  }, [deviceIdFromUrl, navigate])

  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const data = await fetchDevicesPayload()
        setDevices((data.devices || []).map((device: Record<string, unknown>) => mapDevice(device)))
      } catch (error) {
        console.error('Failed to fetch devices:', error)
      } finally {
        setDevicesLoaded(true)
      }
    }

    void fetchDevices()
    const interval = window.setInterval(fetchDevices, 5000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    const fetchDeviceInfo = async () => {
      if (!selectedDevice) {
        setDeviceInfo(null)
        return
      }
      try {
        const data = await fetchDeviceScreenInfo(selectedDevice)
        const resolution = data.screen_resolution || data.screenResolution || '1080x1920'
        const [width, height] = resolution.split('x').map(Number)
        setDeviceInfo({ width: width || 1080, height: height || 1920 })
      } catch {
        setDeviceInfo({ width: 1080, height: 1920 })
      }
    }

    void fetchDeviceInfo()
  }, [selectedDevice])

  return {
    devices,
    devicesLoaded,
    selectedDevice,
    setSelectedDevice,
    currentDevice,
    deviceInfo,
    setDeviceInfo,
  }
}
