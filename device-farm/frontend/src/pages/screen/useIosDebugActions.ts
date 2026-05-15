import { useCallback, useEffect, useRef, useState, type MouseEvent, type PointerEvent } from 'react'
import { message } from 'antd'
import type {
  RenderMetrics,
  StaticDebugActionResponse,
  StaticDebugPoint,
  UIElementNode,
} from './types'
import {
  fetchDeviceScreenshot,
  postIOSDebugAction,
  releaseDebugSession,
} from './api'

interface UseIosDebugActionsOptions {
  selectedDevice: string
  isIosStaticDebug: boolean
  isIosDirectMjpegMirror: boolean
  isIosLivePreview: boolean
  isIosStaticActionSupported: boolean
  renderMetrics: RenderMetrics | null
  uiScreen: { width: number; height: number } | null
  loadingUiHierarchy: boolean
  selectedUiElement: UIElementNode | null
  setUiScreen: (screen: { width: number; height: number }) => void
  setDeviceInfo: (info: { width: number; height: number }) => void
}

export default function useIosDebugActions({
  selectedDevice,
  isIosStaticDebug,
  isIosDirectMjpegMirror,
  isIosLivePreview,
  isIosStaticActionSupported,
  renderMetrics,
  uiScreen,
  loadingUiHierarchy,
  selectedUiElement,
  setUiScreen,
  setDeviceInfo,
}: UseIosDebugActionsOptions) {
  const [staticScreenshot, setStaticScreenshot] = useState<string | null>(null)
  const [staticScreenshotLoading, setStaticScreenshotLoading] = useState(false)
  const [staticActionLoading, setStaticActionLoading] = useState(false)
  const [iosTapMode, setIosTapMode] = useState(false)
  const [iosSwipeMode, setIosSwipeMode] = useState(false)
  const [staticAutoRefresh, setStaticAutoRefresh] = useState(false)
  const [staticAutoRefreshIntervalMs, setStaticAutoRefreshIntervalMs] = useState(1000)
  const [staticRefreshDurationMs, setStaticRefreshDurationMs] = useState<number | null>(null)
  const [staticRefreshFailures, setStaticRefreshFailures] = useState(0)
  const [staticRefreshLastError, setStaticRefreshLastError] = useState('')
  const [staticDebugSessionActive, setStaticDebugSessionActive] = useState(false)
  const [staticPointerPoint, setStaticPointerPoint] = useState<StaticDebugPoint | null>(null)
  const [lastStaticAction, setLastStaticAction] = useState('未操作')
  const [lastIosControlStatus, setLastIosControlStatus] = useState('未操作')

  const staticDragStartRef = useRef<StaticDebugPoint | null>(null)
  const staticSwipeHandledRef = useRef(false)
  const staticActionLoadingRef = useRef(false)
  const staticScreenshotLoadingRef = useRef(false)
  const loadingUiHierarchyRef = useRef(false)

  useEffect(() => {
    staticActionLoadingRef.current = staticActionLoading
  }, [staticActionLoading])

  useEffect(() => {
    staticScreenshotLoadingRef.current = staticScreenshotLoading
  }, [staticScreenshotLoading])

  useEffect(() => {
    loadingUiHierarchyRef.current = loadingUiHierarchy
  }, [loadingUiHierarchy])

  const resetStaticDebugState = useCallback(() => {
    setStaticScreenshot(null)
    setStaticPointerPoint(null)
    setLastStaticAction('未操作')
    setStaticAutoRefresh(false)
    setStaticRefreshDurationMs(null)
    setStaticRefreshFailures(0)
    setStaticRefreshLastError('')
    setStaticDebugSessionActive(false)
  }, [])

  const releaseStaticDebugSession = useCallback((deviceId: string) => {
    void releaseDebugSession(deviceId)
  }, [])

  useEffect(() => {
    resetStaticDebugState()
    if (!selectedDevice || !isIosStaticDebug) return
    return () => {
      setStaticDebugSessionActive(false)
      releaseStaticDebugSession(selectedDevice)
    }
  }, [isIosStaticDebug, releaseStaticDebugSession, resetStaticDebugState, selectedDevice])

  const applyStaticActionScreen = useCallback((data: StaticDebugActionResponse) => {
    if (data.screen?.width && data.screen?.height) {
      setUiScreen({ width: data.screen.width, height: data.screen.height })
      setDeviceInfo({ width: data.screen.width, height: data.screen.height })
    }
  }, [setDeviceInfo, setUiScreen])

  const formatIosControlStatus = useCallback((label: string, data?: StaticDebugActionResponse) => {
    if (typeof data?.latency_ms === 'number') {
      return `${Math.round(data.latency_ms)}ms / ${data.control_method || label}`
    }
    return label
  }, [])

  const refreshStaticScreenshot = useCallback(async (silent = false, timeoutMs = 90000, retryRebuild = true) => {
    if (!selectedDevice || !isIosStaticDebug) return false
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)
    const startedAt = performance.now()

    setStaticScreenshotLoading(true)
    try {
      let data: Record<string, unknown>
      try {
        data = await fetchDeviceScreenshot(selectedDevice, controller.signal)
      } catch (error) {
        if (!retryRebuild || (error as Error).name === 'AbortError') {
          throw error
        }
        setStaticDebugSessionActive(false)
        await releaseDebugSession(selectedDevice)
        data = await fetchDeviceScreenshot(selectedDevice, controller.signal)
      }

      const image = typeof data.image === 'string' ? data.image : ''
      const format = typeof data.format === 'string' ? data.format : 'png'
      const screen = data.screen as { width?: number; height?: number } | undefined
      setStaticScreenshot(`data:image/${format};base64,${image}`)
      if (screen?.width && screen?.height) {
        setUiScreen({ width: screen.width, height: screen.height })
        setDeviceInfo({ width: screen.width, height: screen.height })
      }
      setStaticRefreshDurationMs(Math.round(performance.now() - startedAt))
      setStaticRefreshFailures(0)
      setStaticRefreshLastError('')
      setStaticDebugSessionActive(true)
      if (!silent) {
        message.success('截图已刷新')
      }
      return true
    } catch (e) {
      const error = e as Error
      setStaticRefreshDurationMs(Math.round(performance.now() - startedAt))
      setStaticRefreshFailures((count) => count + 1)
      setStaticRefreshLastError(error.message || '刷新截图失败')
      if (!silent) {
        message.error(error.message || '刷新截图失败')
      }
      return false
    } finally {
      window.clearTimeout(timeoutId)
      setStaticScreenshotLoading(false)
    }
  }, [isIosStaticDebug, selectedDevice, setDeviceInfo, setUiScreen])

  const postStaticDebugAction = useCallback(async (
    path: 'tap' | 'text' | 'swipe' | 'long-press' | 'clear-text',
    payload: Record<string, unknown>,
  ): Promise<StaticDebugActionResponse> => {
    if (!selectedDevice || !isIosStaticActionSupported) {
      throw new Error('当前设备不支持 iOS 静态操作')
    }

    const data = await postIOSDebugAction(selectedDevice, path, payload, {
      isIosDirectMjpegMirror,
      includeScreen: isIosStaticDebug && !isIosDirectMjpegMirror,
    })
    setStaticDebugSessionActive(true)
    return data
  }, [isIosDirectMjpegMirror, isIosStaticActionSupported, isIosStaticDebug, selectedDevice])

  const runStaticTap = useCallback(async (x: number, y: number, label = '点按已发送') => {
    if (isIosStaticDebug) {
      setStaticActionLoading(true)
    }
    try {
      const data = await postStaticDebugAction('tap', { x, y })
      applyStaticActionScreen(data)
      if (isIosStaticDebug) {
        await refreshStaticScreenshot(true)
        message.success(label)
      }
      setLastIosControlStatus(formatIosControlStatus('tap', data))
      setLastStaticAction(`${label} (${Math.round(x)}, ${Math.round(y)})`)
      return true
    } catch (e) {
      const error = e as Error
      message.error(error.message || 'iOS 点按失败')
      setLastStaticAction('点按失败')
      return false
    } finally {
      if (isIosStaticDebug) {
        setStaticActionLoading(false)
      }
    }
  }, [applyStaticActionScreen, formatIosControlStatus, isIosStaticDebug, postStaticDebugAction, refreshStaticScreenshot])

  const runStaticSwipe = useCallback(async (start: StaticDebugPoint, end: StaticDebugPoint) => {
    if (isIosStaticDebug) {
      setStaticActionLoading(true)
    }
    try {
      const data = await postStaticDebugAction('swipe', {
        startX: start.x,
        startY: start.y,
        endX: end.x,
        endY: end.y,
        durationMs: 500,
      })
      applyStaticActionScreen(data)
      if (isIosStaticDebug) {
        await refreshStaticScreenshot(true)
        message.success('滑动已发送')
      }
      setLastIosControlStatus(formatIosControlStatus('swipe', data))
      setLastStaticAction(`滑动 (${start.x}, ${start.y}) -> (${end.x}, ${end.y})`)
      return true
    } catch (e) {
      const error = e as Error
      message.error(error.message || 'iOS 滑动失败')
      setLastStaticAction('滑动失败')
      return false
    } finally {
      if (isIosStaticDebug) {
        setStaticActionLoading(false)
      }
    }
  }, [applyStaticActionScreen, formatIosControlStatus, isIosStaticDebug, postStaticDebugAction, refreshStaticScreenshot])

  const runStaticLongPress = useCallback(async (x: number, y: number, label = '长按已发送') => {
    if (isIosStaticDebug) {
      setStaticActionLoading(true)
    }
    try {
      const data = await postStaticDebugAction('long-press', { x, y, durationMs: 800 })
      applyStaticActionScreen(data)
      if (isIosStaticDebug) {
        await refreshStaticScreenshot(true)
        message.success(label)
      }
      setLastIosControlStatus(formatIosControlStatus('long-press', data))
      setLastStaticAction(`${label} (${Math.round(x)}, ${Math.round(y)})`)
      return true
    } catch (e) {
      const error = e as Error
      message.error(error.message || 'iOS 长按失败')
      setLastStaticAction('长按失败')
      return false
    } finally {
      if (isIosStaticDebug) {
        setStaticActionLoading(false)
      }
    }
  }, [applyStaticActionScreen, formatIosControlStatus, isIosStaticDebug, postStaticDebugAction, refreshStaticScreenshot])

  const sendIosText = useCallback(async (text: string) => {
    if (!isIosStaticActionSupported) return false
    if (isIosStaticDebug) {
      setStaticActionLoading(true)
    }
    try {
      const data = await postStaticDebugAction('text', { text })
      applyStaticActionScreen(data)
      if (isIosStaticDebug) {
        await refreshStaticScreenshot(true)
      }
      message.success('文本已发送')
      setLastIosControlStatus(formatIosControlStatus('text', data))
      setLastStaticAction(`输入文本 (${text.length} 字符)`)
      return true
    } catch (e) {
      const error = e as Error
      message.error(error.message || 'iOS 文本输入失败，请先点按输入框获取焦点')
      setLastStaticAction('输入失败')
      return false
    } finally {
      if (isIosStaticDebug) {
        setStaticActionLoading(false)
      }
    }
  }, [applyStaticActionScreen, formatIosControlStatus, isIosStaticActionSupported, isIosStaticDebug, postStaticDebugAction, refreshStaticScreenshot])

  const clearStaticText = useCallback(async () => {
    if (!isIosStaticActionSupported) return false
    if (isIosStaticDebug) {
      setStaticActionLoading(true)
    }
    try {
      const data = await postStaticDebugAction('clear-text', {})
      applyStaticActionScreen(data)
      if (isIosStaticDebug) {
        await refreshStaticScreenshot(true)
      }
      message.success('输入框已清空')
      setLastIosControlStatus(formatIosControlStatus('clear', data))
      setLastStaticAction('清空输入')
      return true
    } catch (e) {
      const error = e as Error
      message.error(error.message || 'iOS 清空输入失败，请先点按输入框获取焦点')
      setLastStaticAction('清空输入失败')
      return false
    } finally {
      if (isIosStaticDebug) {
        setStaticActionLoading(false)
      }
    }
  }, [applyStaticActionScreen, formatIosControlStatus, isIosStaticActionSupported, isIosStaticDebug, postStaticDebugAction, refreshStaticScreenshot])

  const handleTouchInput = useCallback(
    (type: string, x: number, y: number, extra?: Record<string, unknown>) => {
      if (isIosLivePreview && isIosStaticActionSupported) {
        if (type === 'touch') {
          const action = extra?.action || 'move'
          setStaticPointerPoint({ x, y })
          if (action === 'down') {
            staticDragStartRef.current = { x, y }
            return true
          }
          if (action === 'move') {
            return true
          }
          if (action === 'up') {
            if (staticSwipeHandledRef.current) {
              staticDragStartRef.current = null
              staticSwipeHandledRef.current = false
              return true
            }
            const start = staticDragStartRef.current
            staticDragStartRef.current = null
            if (!start) return true
            const distance = Math.hypot(x - start.x, y - start.y)
            if (distance < 12) {
              void runStaticTap(x, y)
            }
            return true
          }
          return true
        }
        if (type === 'swipe') {
          const endX = Number(extra?.endX)
          const endY = Number(extra?.endY)
          if (Number.isFinite(endX) && Number.isFinite(endY)) {
            staticSwipeHandledRef.current = true
            window.setTimeout(() => {
              staticSwipeHandledRef.current = false
            }, 0)
            void runStaticSwipe({ x, y }, { x: Math.round(endX), y: Math.round(endY) })
          }
          return true
        }
        if (type === 'long-press') {
          staticSwipeHandledRef.current = true
          void runStaticLongPress(x, y)
          return true
        }
      }
      if (isIosStaticDebug && isIosStaticActionSupported) {
        if (type === 'touch') {
          const action = extra?.action || 'move'
          setStaticPointerPoint({ x, y })
          if (iosTapMode && action === 'up' && !staticActionLoadingRef.current) {
            void runStaticTap(x, y)
          }
          return true
        }
        if (type === 'swipe' && iosSwipeMode && !staticActionLoadingRef.current) {
          const endX = Number(extra?.endX)
          const endY = Number(extra?.endY)
          if (Number.isFinite(endX) && Number.isFinite(endY)) {
            staticSwipeHandledRef.current = true
            window.setTimeout(() => {
              staticSwipeHandledRef.current = false
            }, 0)
            void runStaticSwipe({ x, y }, { x: Math.round(endX), y: Math.round(endY) })
          }
          return true
        }
      }
      return false
    },
    [
      iosSwipeMode,
      iosTapMode,
      isIosLivePreview,
      isIosStaticActionSupported,
      isIosStaticDebug,
      runStaticLongPress,
      runStaticSwipe,
      runStaticTap,
    ]
  )

  const pointFromStaticPosition = useCallback((clientX: number, clientY: number, target: HTMLDivElement) => {
    if (!renderMetrics || !uiScreen) return null

    const rect = target.getBoundingClientRect()
    const rawX = clientX - rect.left - renderMetrics.left
    const rawY = clientY - rect.top - renderMetrics.top
    if (rawX < 0 || rawY < 0 || rawX > renderMetrics.width || rawY > renderMetrics.height) {
      return null
    }

    return {
      x: Math.round((rawX / renderMetrics.width) * uiScreen.width),
      y: Math.round((rawY / renderMetrics.height) * uiScreen.height),
    }
  }, [renderMetrics, uiScreen])

  const pointFromStaticClick = useCallback((event: MouseEvent<HTMLDivElement>) => {
    return pointFromStaticPosition(event.clientX, event.clientY, event.currentTarget)
  }, [pointFromStaticPosition])

  const handleStaticStageClick = useCallback((event: MouseEvent<HTMLDivElement>) => {
    if (staticSwipeHandledRef.current) {
      staticSwipeHandledRef.current = false
      return
    }
    if (!iosTapMode || staticActionLoading || !staticScreenshot) return
    const point = pointFromStaticClick(event)
    if (!point) return
    void runStaticTap(point.x, point.y)
  }, [iosTapMode, pointFromStaticClick, runStaticTap, staticActionLoading, staticScreenshot])

  const handleStaticStagePointerMove = useCallback((event: PointerEvent<HTMLDivElement>) => {
    const point = pointFromStaticPosition(event.clientX, event.clientY, event.currentTarget)
    setStaticPointerPoint(point)
  }, [pointFromStaticPosition])

  const handleStaticStagePointerDown = useCallback((event: PointerEvent<HTMLDivElement>) => {
    const point = pointFromStaticPosition(event.clientX, event.clientY, event.currentTarget)
    setStaticPointerPoint(point)
    if (!iosSwipeMode || staticActionLoading || !staticScreenshot || !point) return

    staticDragStartRef.current = point
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }, [iosSwipeMode, pointFromStaticPosition, staticActionLoading, staticScreenshot])

  const handleStaticStagePointerUp = useCallback((event: PointerEvent<HTMLDivElement>) => {
    const start = staticDragStartRef.current
    staticDragStartRef.current = null
    const point = pointFromStaticPosition(event.clientX, event.clientY, event.currentTarget)
    setStaticPointerPoint(point)
    event.currentTarget.releasePointerCapture?.(event.pointerId)
    if (!iosSwipeMode || staticActionLoading || !staticScreenshot || !start || !point) return

    const distance = Math.hypot(point.x - start.x, point.y - start.y)
    if (distance < 12) return

    staticSwipeHandledRef.current = true
    window.setTimeout(() => {
      staticSwipeHandledRef.current = false
    }, 0)
    void runStaticSwipe(start, point)
  }, [iosSwipeMode, pointFromStaticPosition, runStaticSwipe, staticActionLoading, staticScreenshot])

  const handleStaticStagePointerCancel = useCallback((event: PointerEvent<HTMLDivElement>) => {
    staticDragStartRef.current = null
    event.currentTarget.releasePointerCapture?.(event.pointerId)
  }, [])

  const tapSelectedUiElement = useCallback(() => {
    if (!selectedUiElement) return
    void runStaticTap(
      selectedUiElement.center.x,
      selectedUiElement.center.y,
      '控件点击已发送',
    )
  }, [runStaticTap, selectedUiElement])

  const longPressSelectedUiElement = useCallback(() => {
    if (!selectedUiElement) return
    void runStaticLongPress(
      selectedUiElement.center.x,
      selectedUiElement.center.y,
      '控件长按已发送',
    )
  }, [runStaticLongPress, selectedUiElement])

  useEffect(() => {
    if (!selectedDevice || !isIosStaticDebug || !staticAutoRefresh) return

    const interval = window.setInterval(() => {
      if (
        staticActionLoadingRef.current
        || staticScreenshotLoadingRef.current
        || loadingUiHierarchyRef.current
      ) {
        return
      }
      void refreshStaticScreenshot(true, 90000)
    }, staticAutoRefreshIntervalMs)

    return () => window.clearInterval(interval)
  }, [isIosStaticDebug, refreshStaticScreenshot, selectedDevice, staticAutoRefresh, staticAutoRefreshIntervalMs])

  return {
    staticScreenshot,
    setStaticScreenshot,
    staticScreenshotLoading,
    staticActionLoading,
    iosTapMode,
    setIosTapMode,
    iosSwipeMode,
    setIosSwipeMode,
    staticAutoRefresh,
    setStaticAutoRefresh,
    staticAutoRefreshIntervalMs,
    setStaticAutoRefreshIntervalMs,
    staticRefreshDurationMs,
    staticRefreshFailures,
    staticRefreshLastError,
    staticDebugSessionActive,
    setStaticDebugSessionActive,
    staticPointerPoint,
    setStaticPointerPoint,
    lastStaticAction,
    setLastStaticAction,
    lastIosControlStatus,
    refreshStaticScreenshot,
    handleTouchInput,
    handleStaticStageClick,
    handleStaticStagePointerDown,
    handleStaticStagePointerMove,
    handleStaticStagePointerUp,
    handleStaticStagePointerCancel,
    tapSelectedUiElement,
    longPressSelectedUiElement,
    sendIosText,
    clearStaticText,
    resetStaticDebugState,
  }
}
