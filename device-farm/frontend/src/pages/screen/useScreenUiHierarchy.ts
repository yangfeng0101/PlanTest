import { useCallback, useMemo, useState } from 'react'
import { message } from 'antd'
import type { Device } from '@/types'
import type { UIElementNode } from './types'
import { fetchUIHierarchy } from './api'
import { buildLocatorSnippets, buildVisibleUiElements } from './uiHierarchy'

interface UseScreenUiHierarchyOptions {
  selectedDevice: string
  currentDevice: Device | undefined
  isIosDevice: boolean
  isIosStaticDebug: boolean
  isIosDirectMjpegMirror: boolean
  setDeviceInfo: (deviceInfo: { width: number; height: number } | null) => void
}

interface FetchUiHierarchyOptions {
  isPlaying: boolean
  refreshStaticScreenshot: (forceRecreateSession?: boolean) => Promise<boolean>
  setStaticDebugSessionActive: (active: boolean) => void
}

export default function useScreenUiHierarchy({
  selectedDevice,
  currentDevice,
  isIosDevice,
  isIosStaticDebug,
  isIosDirectMjpegMirror,
  setDeviceInfo,
}: UseScreenUiHierarchyOptions) {
  const [uiElements, setUiElements] = useState<UIElementNode[]>([])
  const [selectedUiElement, setSelectedUiElement] = useState<UIElementNode | null>(null)
  const [loadingUiHierarchy, setLoadingUiHierarchy] = useState(false)
  const [uiScreen, setUiScreen] = useState<{ width: number; height: number } | null>(null)

  const clearUiHierarchy = useCallback(() => {
    setUiElements([])
    setSelectedUiElement(null)
    setUiScreen(null)
  }, [])

  const applyUiScreen = useCallback((screen?: { width?: number; height?: number } | null) => {
    const width = Number(screen?.width)
    const height = Number(screen?.height)
    if (width > 0 && height > 0) {
      setUiScreen({ width, height })
      setDeviceInfo({ width, height })
    }
  }, [setDeviceInfo])

  const fetchUiHierarchy = useCallback(async ({
    isPlaying,
    refreshStaticScreenshot,
    setStaticDebugSessionActive,
  }: FetchUiHierarchyOptions) => {
    if (!selectedDevice) return
    if (!isPlaying && !isIosStaticDebug) {
      message.warning('请先连接投屏后再获取控件')
      return
    }
    if (currentDevice && !currentDevice.capabilities.uiHierarchy) {
      message.warning('当前设备连接不支持获取控件')
      return
    }

    setLoadingUiHierarchy(true)
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), isIosStaticDebug ? 90000 : 18000)
    try {
      if (isIosStaticDebug) {
        const screenshotOk = await refreshStaticScreenshot(true)
        if (!screenshotOk) {
          message.warning('截图刷新失败，但会继续尝试获取控件树')
        }
      }
      const result = await fetchUIHierarchy(selectedDevice, isIosDirectMjpegMirror, controller.signal)
      setUiElements(result.elements || [])
      setSelectedUiElement(null)
      if (result.screen?.width > 0 && result.screen?.height > 0) {
        setUiScreen({ width: result.screen.width, height: result.screen.height })
        if (isIosDevice) {
          setDeviceInfo({ width: result.screen.width, height: result.screen.height })
        }
      }
      if (isIosStaticDebug) {
        setStaticDebugSessionActive(true)
      }
      message.success(`获取到 ${result.elements?.length || 0} 个控件，点击控件框查看属性`)
    } catch (error) {
      const fetchError = error as Error
      if (fetchError.name === 'AbortError') {
        message.error('获取控件超时，请确认设备页面已稳定后重试')
      } else {
        message.error(fetchError.message || '获取控件失败')
      }
    } finally {
      window.clearTimeout(timeoutId)
      setLoadingUiHierarchy(false)
    }
  }, [
    currentDevice,
    isIosDevice,
    isIosDirectMjpegMirror,
    isIosStaticDebug,
    selectedDevice,
    setDeviceInfo,
  ])

  const visibleUiElements = useMemo(
    () => buildVisibleUiElements(uiElements, uiScreen, isIosDevice),
    [isIosDevice, uiElements, uiScreen],
  )
  const locatorSnippets = useMemo(
    () => buildLocatorSnippets(selectedUiElement, isIosDevice ? 'ios' : 'android'),
    [isIosDevice, selectedUiElement],
  )

  return {
    uiElements,
    selectedUiElement,
    setSelectedUiElement,
    loadingUiHierarchy,
    uiScreen,
    setUiScreen,
    clearUiHierarchy,
    applyUiScreen,
    fetchUiHierarchy,
    visibleUiElements,
    locatorSnippets,
  }
}
