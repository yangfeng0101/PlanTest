import { useEffect, useRef, useState, useCallback, useMemo, type MouseEvent, type PointerEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Typography, message } from 'antd'
import type { Room } from 'livekit-client'
import type { Device, Script, Task, TaskLogEntry } from '@/types'
import { scriptApi, taskApi } from '@/services/api'
import { formatDeviceOs, mapDevice } from '@/utils/device'
import type {
  LocatorSnippet,
  RenderMetrics,
  ScreenSessionDiagnostics,
  StaticDebugActionResponse,
  StaticDebugPoint,
  UIElementNode,
  WorkspaceTab,
} from './types'
import { buildLocatorSnippets, buildVisibleUiElements } from './uiHierarchy'
import {
  IOS_DIRECT_MJPEG_SCREEN_DRIVERS,
  KEYBOARD_KEY_CODE_MAP,
  TOUCH_MOVE_INTERVAL_MS,
  buildIOSMJPEGStreamUrl,
  fetchDeviceScreenInfo,
  fetchDeviceScreenshot,
  fetchDevicesPayload,
  fetchSessionDiagnostics,
  fetchUIHierarchy,
  postIOSDebugAction,
  prepareIOSMJPEGSession,
  releaseDebugSession,
  requestReleaseDebugSession,
  requestStopIOSMJPEG,
  requestStopSession,
  startLiveKitSession,
} from './api'
import {
  buildDebugTags,
  countScriptLines,
  createDefaultScreenScript,
  findLatestScriptLine,
  isActiveTask,
  visibleDebugLogs as filterVisibleDebugLogs,
} from './scriptWorkspace'
import DeviceStagePanel from './DeviceStagePanel'
import InspectorPanel from './InspectorPanel'
import ScriptWorkspacePanel from './ScriptWorkspacePanel'
import ScriptModals from './ScriptModals'
import './ScreenPage.css'

const { Text } = Typography

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false
  const tagName = target.tagName.toLowerCase()
  return tagName === 'input' || tagName === 'textarea' || target.isContentEditable
}

export default function ScreenPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const deviceIdFromUrl = searchParams.get('deviceId')
  const missingDeviceMessageShownRef = useRef(false)
  const playerViewportRef = useRef<HTMLDivElement>(null)
  const playerContainerRef = useRef<HTMLDivElement>(null)

  const [devices, setDevices] = useState<Device[]>([])
  const [devicesLoaded, setDevicesLoaded] = useState(false)
  const [selectedDevice, setSelectedDevice] = useState<string>(deviceIdFromUrl || '')
  const [deviceInfo, setDeviceInfo] = useState<{ width: number; height: number } | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(Boolean(deviceIdFromUrl))
  const [fps, setFps] = useState(0)
  const [hasVideoFrame, setHasVideoFrame] = useState(false)
  const [uiElements, setUiElements] = useState<UIElementNode[]>([])
  const [selectedUiElement, setSelectedUiElement] = useState<UIElementNode | null>(null)
  const [loadingUiHierarchy, setLoadingUiHierarchy] = useState(false)
  const [playerBoxSize, setPlayerBoxSize] = useState<{ width: number; height: number } | null>(null)
  const [renderMetrics, setRenderMetrics] = useState<RenderMetrics | null>(null)
  const [uiScreen, setUiScreen] = useState<{ width: number; height: number } | null>(null)
  const [sessionDiagnostics, setSessionDiagnostics] = useState<ScreenSessionDiagnostics | null>(null)
  const [browserFirstFrameMs, setBrowserFirstFrameMs] = useState<number | null>(null)
  const [networkLatencyMs, setNetworkLatencyMs] = useState<number | null>(null)
  const [quickInputText, setQuickInputText] = useState('')
  const [virtualKeyboardOpen, setVirtualKeyboardOpen] = useState(false)
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<WorkspaceTab>('inspect')
  const [scriptSaving, setScriptSaving] = useState(false)
  const [scriptSaveModalOpen, setScriptSaveModalOpen] = useState(false)
  const [scriptPickerOpen, setScriptPickerOpen] = useState(false)
  const [scriptPickerLoading, setScriptPickerLoading] = useState(false)
  const [savedScripts, setSavedScripts] = useState<Script[]>([])
  const [scriptName, setScriptName] = useState('')
  const [scriptDescription, setScriptDescription] = useState('')
  const [scriptTags, setScriptTags] = useState<string[]>(['screen-debug'])
  const [scriptContent, setScriptContent] = useState('')
  const [loadedScript, setLoadedScript] = useState<Script | null>(null)
  const [debugScriptId, setDebugScriptId] = useState<string | null>(null)
  const [debugTask, setDebugTask] = useState<Task | null>(null)
  const [debugTaskLogs, setDebugTaskLogs] = useState<TaskLogEntry[]>([])
  const [debugSubmitting, setDebugSubmitting] = useState(false)
  const [debugCanceling, setDebugCanceling] = useState(false)
  const [debugCurrentLine, setDebugCurrentLine] = useState<number | null>(null)
  const [debugScriptSnapshot, setDebugScriptSnapshot] = useState('')
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
  const [mjpegStreamKey, setMjpegStreamKey] = useState(0)
  const currentDevice = devices.find((d) => d.id === selectedDevice)
  const screenMirrorSupported = currentDevice?.capabilities.screenMirror ?? false
  const remoteControlSupported = currentDevice?.capabilities.remoteControl ?? false
  const uiHierarchySupported = currentDevice?.capabilities.uiHierarchy ?? false
  const screenshotSupported = currentDevice?.capabilities.screenshot ?? false
  const isIosDevice = Boolean(currentDevice && currentDevice.os.toLowerCase() === 'ios')
  const screenDriver = (currentDevice?.drivers.screen || '').trim().toLowerCase()
  const isIosDirectMjpegMirror = Boolean(
    isIosDevice
    && screenMirrorSupported
    && IOS_DIRECT_MJPEG_SCREEN_DRIVERS.has(screenDriver)
  )
  const isIosLivePreview = isIosDirectMjpegMirror
  const isIosStaticDebug = Boolean(
    isIosDevice
    && !screenMirrorSupported
    && uiHierarchySupported
    && screenshotSupported
  )
  const isIosStaticActionSupported = Boolean(isIosDevice && uiHierarchySupported && screenshotSupported)
  const isIosTextInputAvailable = Boolean(isIosStaticActionSupported && (isIosStaticDebug || isPlaying))
  const iosModeLabel = isIosDirectMjpegMirror
    ? 'iOS MJPEG 直连预览'
    : 'iOS 静态预览'
  
  // LiveKit state
  const [lkSession, setLkSession] = useState<{ url: string; token: string } | null>(null)
  const lkRoomRef = useRef<Room | null>(null)
  const pendingMoveRef = useRef<{ x: number; y: number } | null>(null)
  const moveTimerRef = useRef<number | null>(null)
  const staticDragStartRef = useRef<StaticDebugPoint | null>(null)
  const staticSwipeHandledRef = useRef(false)
  const staticActionLoadingRef = useRef(false)
  const staticScreenshotLoadingRef = useRef(false)
  const loadingUiHierarchyRef = useRef(false)
  const autoStartedDeviceRef = useRef<string | null>(null)
  const autoStartBlockedRef = useRef<string | null>(null)
  const startRequestedAtRef = useRef<number | null>(null)
  const activeSessionDeviceRef = useRef<string | null>(null)
  const activeSessionKindRef = useRef<'livekit' | 'ios-mjpeg' | null>(null)

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
    staticActionLoadingRef.current = staticActionLoading
  }, [staticActionLoading])

  useEffect(() => {
    staticScreenshotLoadingRef.current = staticScreenshotLoading
  }, [staticScreenshotLoading])

  useEffect(() => {
    loadingUiHierarchyRef.current = loadingUiHierarchy
  }, [loadingUiHierarchy])

  // Fetch devices
  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const data = await fetchDevicesPayload()
        setDevices((data.devices || []).map((d: Record<string, unknown>) => mapDevice(d)))
      } catch (e) {
        console.error('Failed to fetch devices:', e)
      } finally {
        setDevicesLoaded(true)
      }
    }
    fetchDevices()
    const interval = setInterval(fetchDevices, 5000)
    return () => clearInterval(interval)
  }, [])

  // Fetch device screen info
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
    fetchDeviceInfo()
  }, [selectedDevice])

  const applyIosLogicalScreen = useCallback((screen?: { width?: number; height?: number } | null) => {
    const width = Number(screen?.width)
    const height = Number(screen?.height)
    if (width > 0 && height > 0) {
      setUiScreen({ width, height })
      setDeviceInfo({ width, height })
    }
  }, [])

  // Start session on backend
  const startSession = useCallback(async () => {
    if (!selectedDevice) return
    if (devicesLoaded && !currentDevice) {
      message.error('未找到当前设备，请回到设备列表重新选择')
      return
    }
    if (currentDevice && currentDevice.status !== 'online') {
      message.error('当前设备不可用，无法投屏')
      return
    }
    if (currentDevice && !currentDevice.capabilities.screenMirror) {
      message.error('当前设备连接不支持投屏')
      return
    }
    if (isIosDevice && !isIosLivePreview) {
      message.error('当前 iOS 投屏 driver 不支持，请使用 mjpeg-direct')
      return
    }
    setLoading(true)
    setSessionDiagnostics(null)
    setBrowserFirstFrameMs(null)
    setNetworkLatencyMs(null)
    startRequestedAtRef.current = performance.now()
    try {
      if (isIosDirectMjpegMirror) {
        const prepareData = await prepareIOSMJPEGSession(selectedDevice)
        applyIosLogicalScreen(prepareData.screen)
        setHasVideoFrame(false)
        setFps(0)
        setLkSession(null)
        setSessionDiagnostics({
          active: true,
          stage: 'streaming',
          stage_label: 'iOS MJPEG direct',
        })
        activeSessionDeviceRef.current = selectedDevice
        activeSessionKindRef.current = 'ios-mjpeg'
        setMjpegStreamKey(Date.now())
        setIsPlaying(true)
        return
      }

      const data = await startLiveKitSession(selectedDevice)
      const videoWidth = Number(data.video_width || data.videoWidth)
      const videoHeight = Number(data.video_height || data.videoHeight)
      if (videoWidth > 0 && videoHeight > 0) {
        setDeviceInfo({ width: videoWidth, height: videoHeight })
      }
      setHasVideoFrame(false)
      setSessionDiagnostics(data)
      activeSessionDeviceRef.current = selectedDevice
      activeSessionKindRef.current = 'livekit'
      setLkSession({ url: data.livekit_url || 'ws://localhost:7880', token: data.token })
      setIsPlaying(true)
    } catch (e) {
      const error = e as Error
      message.error(error.message || '启动会话失败')
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [applyIosLogicalScreen, currentDevice, devicesLoaded, isIosDevice, isIosDirectMjpegMirror, isIosLivePreview, selectedDevice])

  useEffect(() => {
    if (!selectedDevice || !devicesLoaded || isPlaying || lkSession || autoStartedDeviceRef.current === selectedDevice) return

    if (!currentDevice) {
      setLoading(false)
      const blockKey = `${selectedDevice}:missing`
      if (autoStartBlockedRef.current !== blockKey) {
        autoStartBlockedRef.current = blockKey
        message.error('未找到当前设备，请回到设备列表重新选择')
      }
      return
    }
    if (currentDevice.status !== 'online') {
      setLoading(false)
      const blockKey = `${selectedDevice}:unavailable:${currentDevice.status}`
      if (autoStartBlockedRef.current !== blockKey) {
        autoStartBlockedRef.current = blockKey
        message.error('当前设备不可用，无法投屏')
      }
      return
    }
    if (isIosStaticDebug) {
      setLoading(false)
      autoStartBlockedRef.current = null
      return
    }
    if (!currentDevice.capabilities.screenMirror) {
      setLoading(false)
      const blockKey = `${selectedDevice}:unsupported`
      if (autoStartBlockedRef.current !== blockKey) {
        autoStartBlockedRef.current = blockKey
        message.error('当前设备连接不支持投屏')
      }
      return
    }
    if (isIosDevice && !isIosLivePreview) {
      setLoading(false)
      const blockKey = `${selectedDevice}:unsupported-ios-driver`
      if (autoStartBlockedRef.current !== blockKey) {
        autoStartBlockedRef.current = blockKey
        message.error('当前 iOS 投屏 driver 不支持，请使用 mjpeg-direct')
      }
      return
    }

    autoStartBlockedRef.current = null
    autoStartedDeviceRef.current = selectedDevice
    void startSession()
  }, [currentDevice, devicesLoaded, isIosDevice, isIosLivePreview, isIosStaticDebug, isPlaying, lkSession, selectedDevice, startSession])

  const stopSession = async () => {
    if (!selectedDevice) return
    setIsPlaying(false)
    setLkSession(null)
    setHasVideoFrame(false)
    setSessionDiagnostics(null)
    setBrowserFirstFrameMs(null)
    setNetworkLatencyMs(null)
    startRequestedAtRef.current = null
    const sessionKind = activeSessionKindRef.current
    activeSessionDeviceRef.current = null
    activeSessionKindRef.current = null
    setMjpegStreamKey(0)
    clearUiHierarchy()
    setStaticScreenshot(null)
    setStaticPointerPoint(null)
    setLastStaticAction('未操作')
    setStaticDebugSessionActive(false)
    flushPendingMove()
    lkRoomRef.current = null
    if (sessionKind === 'ios-mjpeg') {
      requestStopIOSMJPEG(selectedDevice)
    }
    requestStopSession(selectedDevice)
  }

  const releaseStaticDebugSession = useCallback((deviceId: string) => {
    requestReleaseDebugSession(deviceId)
  }, [])

  const publishControl = useCallback((payload: Record<string, unknown>, reliable = false) => {
    const room = lkRoomRef.current
    if (!room || room.state !== 'connected') return

    const encoder = new TextEncoder()
    void room.localParticipant.publishData(encoder.encode(JSON.stringify(payload)), {
      reliable,
      topic: 'control',
    })
  }, [])

  const sendAndroidKey = useCallback((keyCode: number) => {
    if (!remoteControlSupported || keyCode <= 0) return

    publishControl({ type: 'key', action: 'down', keyCode }, true)
    window.setTimeout(() => {
      publishControl({ type: 'key', action: 'up', keyCode }, true)
    }, 50)
  }, [publishControl, remoteControlSupported])

  const flushPendingMove = useCallback(() => {
    if (moveTimerRef.current) {
      window.clearTimeout(moveTimerRef.current)
      moveTimerRef.current = null
    }

    const pendingMove = pendingMoveRef.current
    pendingMoveRef.current = null
    if (pendingMove) {
      publishControl({ type: 'touch', action: 'move', x: pendingMove.x, y: pendingMove.y }, false)
    }
  }, [publishControl])

  const scheduleMove = useCallback(
    (x: number, y: number) => {
      pendingMoveRef.current = { x, y }
      if (moveTimerRef.current) return

      moveTimerRef.current = window.setTimeout(() => {
        moveTimerRef.current = null
        const pendingMove = pendingMoveRef.current
        pendingMoveRef.current = null
        if (pendingMove) {
          publishControl({ type: 'touch', action: 'move', x: pendingMove.x, y: pendingMove.y }, false)
        }
      }, TOUCH_MOVE_INTERVAL_MS)
    },
    [publishControl]
  )

  const handleWebRTCStats = useCallback((stats: { fps: number; bytesReceived: number; latencyMs?: number }) => {
    setFps(stats.fps)
    if (typeof stats.latencyMs === 'number') {
      setNetworkLatencyMs(stats.latencyMs)
    }
  }, [])

  const clearUiHierarchy = useCallback(() => {
    setUiElements([])
    setSelectedUiElement(null)
    setUiScreen(null)
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
  }, [isIosStaticDebug, selectedDevice])

  const fetchUiHierarchy = useCallback(async () => {
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
    } catch (e) {
      const error = e as Error
      if (error.name === 'AbortError') {
        message.error('获取控件超时，请确认设备页面已稳定后重试')
      } else {
        message.error(error.message || '获取控件失败')
      }
    } finally {
      window.clearTimeout(timeoutId)
      setLoadingUiHierarchy(false)
    }
  }, [currentDevice, isIosDevice, isIosDirectMjpegMirror, isIosStaticDebug, isPlaying, refreshStaticScreenshot, selectedDevice])

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

  const applyStaticActionScreen = useCallback((data: StaticDebugActionResponse) => {
    if (data.screen?.width && data.screen?.height) {
      setUiScreen({ width: data.screen.width, height: data.screen.height })
      setDeviceInfo({ width: data.screen.width, height: data.screen.height })
    }
  }, [])

  const formatIosControlStatus = useCallback((label: string, data?: StaticDebugActionResponse) => {
    if (typeof data?.latency_ms === 'number') {
      return `${Math.round(data.latency_ms)}ms / ${data.control_method || label}`
    }
    return label
  }, [])

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

  // Handle touch input from LiveKit overlay. Android/Harmony goes through the
  // realtime scrcpy channel; iOS live video still uses the static Appium action
  // endpoints so it does not advertise full remoteControl.
  const handleTouchInput = useCallback(
    (type: string, x: number, y: number, extra?: Record<string, unknown>) => {
      if (isIosLivePreview && isIosStaticActionSupported) {
        if (type === 'touch') {
          const action = extra?.action || 'move'
          setStaticPointerPoint({ x, y })
          if (action === 'down') {
            staticDragStartRef.current = { x, y }
            return
          }
          if (action === 'move') {
            return
          }
          if (action === 'up') {
            if (staticSwipeHandledRef.current) {
              staticDragStartRef.current = null
              staticSwipeHandledRef.current = false
              return
            }
            const start = staticDragStartRef.current
            staticDragStartRef.current = null
            if (!start) return
            const distance = Math.hypot(x - start.x, y - start.y)
            if (distance < 12) {
              void runStaticTap(x, y)
            }
            return
          }
          return
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
          return
        }
        if (type === 'long-press') {
          staticSwipeHandledRef.current = true
          void runStaticLongPress(x, y)
          return
        }
      }
      if (isIosStaticDebug && isIosStaticActionSupported) {
        if (type === 'touch') {
          const action = extra?.action || 'move'
          setStaticPointerPoint({ x, y })
          if (iosTapMode && action === 'up' && !staticActionLoadingRef.current) {
            void runStaticTap(x, y)
          }
          return
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
          return
        }
      }
      if (!remoteControlSupported) return
      if (type !== 'touch') return
      const action = extra?.action || 'move'
      if (action === 'move') {
        scheduleMove(x, y)
        return
      }

      flushPendingMove()
      publishControl({ type: 'touch', action, x, y }, true)
    },
    [
      flushPendingMove,
      iosSwipeMode,
      iosTapMode,
      isIosLivePreview,
      isIosStaticActionSupported,
      isIosStaticDebug,
      publishControl,
      remoteControlSupported,
      runStaticLongPress,
      runStaticSwipe,
      runStaticTap,
      scheduleMove,
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

  const handleConnectionStateChange = useCallback((state: string) => {
    if (state === 'disconnected') {
      setHasVideoFrame(false)
    }
    if (state === 'connected') {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!selectedDevice || !isPlaying || hasVideoFrame || isIosDirectMjpegMirror) return

    let cancelled = false
    const refreshSessionDiagnostics = async () => {
      try {
        const data = await fetchSessionDiagnostics(selectedDevice)
        if (!cancelled) {
          setSessionDiagnostics(data)
        }
      } catch (e) {
        console.error('Failed to fetch screen session diagnostics:', e)
      }
    }

    void refreshSessionDiagnostics()
    const interval = window.setInterval(refreshSessionDiagnostics, 1000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [hasVideoFrame, isIosDirectMjpegMirror, isPlaying, selectedDevice])

  useEffect(() => {
    return () => {
      if (moveTimerRef.current) {
        window.clearTimeout(moveTimerRef.current)
      }
      const activeDevice = activeSessionDeviceRef.current
      if (activeDevice) {
        if (activeSessionKindRef.current === 'ios-mjpeg') {
          requestStopIOSMJPEG(activeDevice)
        }
        requestStopSession(activeDevice)
      }
    }
  }, [])

  useEffect(() => {
    setStaticScreenshot(null)
    setStaticPointerPoint(null)
    setLastStaticAction('未操作')
    setStaticAutoRefresh(false)
    setStaticRefreshDurationMs(null)
    setStaticRefreshFailures(0)
    setStaticRefreshLastError('')
    setStaticDebugSessionActive(false)
    if (!selectedDevice || !isIosStaticDebug) return
    return () => {
      setStaticDebugSessionActive(false)
      releaseStaticDebugSession(selectedDevice)
    }
  }, [isIosStaticDebug, releaseStaticDebugSession, selectedDevice])

  useEffect(() => {
    if (!virtualKeyboardOpen || !isPlaying || !remoteControlSupported) return

    const handleKeyboardInput = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return
      if (isEditableTarget(event.target)) return

      const keyCode = KEYBOARD_KEY_CODE_MAP[event.key]
      if (keyCode) {
        event.preventDefault()
        sendAndroidKey(keyCode)
        return
      }

      if (event.key.length === 1) {
        event.preventDefault()
        publishControl({ type: 'text', text: event.key }, true)
      }
    }

    window.addEventListener('keydown', handleKeyboardInput)
    return () => window.removeEventListener('keydown', handleKeyboardInput)
  }, [isPlaying, publishControl, remoteControlSupported, sendAndroidKey, virtualKeyboardOpen])

  useEffect(() => {
    const container = playerContainerRef.current
    if (!container || !deviceInfo) {
      setRenderMetrics(null)
      return
    }

    const updateMetrics = () => {
      const rect = container.getBoundingClientRect()
      const screenRatio = deviceInfo.width / deviceInfo.height
      const containerRatio = rect.width / rect.height
      const width = containerRatio > screenRatio ? rect.height * screenRatio : rect.width
      const height = containerRatio > screenRatio ? rect.height : rect.width / screenRatio
      setRenderMetrics({
        left: (rect.width - width) / 2,
        top: (rect.height - height) / 2,
        width,
        height,
      })
    }

    updateMetrics()
    const observer = new ResizeObserver(updateMetrics)
    observer.observe(container)
    window.addEventListener('resize', updateMetrics)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', updateMetrics)
    }
  }, [deviceInfo, isPlaying])

  useEffect(() => {
    const viewport = playerViewportRef.current
    if (!viewport || !deviceInfo) {
      setPlayerBoxSize(null)
      return
    }

    const updateBoxSize = () => {
      const rect = viewport.getBoundingClientRect()
      if (rect.width <= 0 || rect.height <= 0) {
        setPlayerBoxSize(null)
        return
      }

      const screenRatio = deviceInfo.width / deviceInfo.height
      const viewportRatio = rect.width / rect.height
      const height = viewportRatio > screenRatio ? rect.height : rect.width / screenRatio
      const width = viewportRatio > screenRatio ? rect.height * screenRatio : rect.width

      setPlayerBoxSize({ width, height })
    }

    updateBoxSize()
    const observer = new ResizeObserver(updateBoxSize)
    observer.observe(viewport)
    window.addEventListener('resize', updateBoxSize)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', updateBoxSize)
    }
  }, [deviceInfo])

  const visibleUiElements = useMemo(
    () => buildVisibleUiElements(uiElements, uiScreen, isIosDevice),
    [isIosDevice, uiElements, uiScreen],
  )
  const locatorSnippets = useMemo(
    () => buildLocatorSnippets(selectedUiElement, isIosDevice ? 'ios' : 'android'),
    [isIosDevice, selectedUiElement],
  )
  const scriptLineCount = useMemo(() => countScriptLines(scriptContent), [scriptContent])
  const visibleDebugLogs = useMemo(
    () => filterVisibleDebugLogs(debugTaskLogs),
    [debugTaskLogs],
  )
  const debugScreenshots = debugTask?.result?.screenshots || []
  const debugTaskActive = isActiveTask(debugTask)
  const debugTaskId = debugTask?.id
  const debugTaskPollingActive = Boolean(debugTask && isActiveTask(debugTask))
  const activeDebugLine = debugScriptSnapshot === scriptContent ? debugCurrentLine : null
  const failedDebugLine = debugTask?.status === 'failed' ? activeDebugLine : null
  const inspectReady = isPlaying || isIosStaticDebug
  const iosMjpegStreamUrl = useMemo(() => {
    if (!selectedDevice || !isPlaying || !isIosDirectMjpegMirror || !mjpegStreamKey) return ''
    return buildIOSMJPEGStreamUrl(selectedDevice, mjpegStreamKey)
  }, [isIosDirectMjpegMirror, isPlaying, mjpegStreamKey, selectedDevice])

  const hasStartupError = !isIosStaticDebug && Boolean(sessionDiagnostics?.last_error)
  const isInitializing = !isIosStaticDebug && !hasVideoFrame && !hasStartupError
  const startupStatusText = '正在初始化设备，请稍后...'
  const statusDotClassName = isIosStaticDebug
    ? 'connected'
    : hasVideoFrame
    ? 'connected'
    : hasStartupError
      ? 'error'
      : 'connecting'

  const applyDebugLogs = (logs: TaskLogEntry[]) => {
    setDebugTaskLogs(logs)
    setDebugCurrentLine(findLatestScriptLine(logs))
  }

  useEffect(() => {
    if (!debugTaskId || !debugTaskPollingActive) return

    let cancelled = false
    const pollTask = async () => {
      try {
        const [taskResponse, logsResponse] = await Promise.all([
          taskApi.getDetail(debugTaskId),
          taskApi.getLogs(debugTaskId, { limit: 1000 }),
        ])
        if (cancelled) return
        setDebugTask(taskResponse.data)
        applyDebugLogs(logsResponse.data)
      } catch (error) {
        console.error('Failed to poll debug task:', error)
      }
    }

    const timer = window.setInterval(pollTask, 2000)
    void pollTask()
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [debugTaskId, debugTaskPollingActive])

  // Send key event via DataChannel
  const sendKey = (keycode: string) => {
    const keyMap: Record<string, number> = {
      'KEYCODE_HOME': 3,
      'KEYCODE_BACK': 4,
      'KEYCODE_APP_SWITCH': 187,
      'KEYCODE_POWER': 26,
    }

    const keyCode = keyMap[keycode]
    if (!keyCode) return
    sendAndroidKey(keyCode)
  }

  const sendText = async () => {
    const text = quickInputText
    if (!text) return

    if (isIosStaticActionSupported) {
      if (isIosStaticDebug) {
        setStaticActionLoading(true)
      }
      try {
        const data = await postStaticDebugAction('text', { text })
        applyStaticActionScreen(data)
        if (isIosStaticDebug) {
          await refreshStaticScreenshot(true)
        }
        setQuickInputText('')
        setVirtualKeyboardOpen(false)
        message.success('文本已发送')
        setLastIosControlStatus(formatIosControlStatus('text', data))
        setLastStaticAction(`输入文本 (${text.length} 字符)`)
      } catch (e) {
        const error = e as Error
        message.error(error.message || 'iOS 文本输入失败，请先点按输入框获取焦点')
        setLastStaticAction('输入失败')
      } finally {
        if (isIosStaticDebug) {
          setStaticActionLoading(false)
        }
      }
      return
    }

    if (!remoteControlSupported) return

    publishControl({ type: 'text', text }, true)
    setQuickInputText('')
    setVirtualKeyboardOpen(false)
  }

  const clearStaticText = async () => {
    if (!isIosStaticActionSupported) return

    if (isIosStaticDebug) {
      setStaticActionLoading(true)
    }
    try {
      const data = await postStaticDebugAction('clear-text', {})
      applyStaticActionScreen(data)
      if (isIosStaticDebug) {
        await refreshStaticScreenshot(true)
      }
      setQuickInputText('')
      message.success('输入框已清空')
      setLastIosControlStatus(formatIosControlStatus('clear', data))
      setLastStaticAction('清空输入')
    } catch (e) {
      const error = e as Error
      message.error(error.message || 'iOS 清空输入失败，请先点按输入框获取焦点')
      setLastStaticAction('清空输入失败')
    } finally {
      if (isIosStaticDebug) {
        setStaticActionLoading(false)
      }
    }
  }

  const getCurrentPackageName = () => (
    selectedUiElement?.package || uiElements.find((element) => element.package)?.package || 'com.example.app'
  )

  const getDefaultScriptName = () => `${currentDevice?.name || selectedDevice || '投屏'} 自动化脚本`

  const ensureScriptDraft = () => {
    const packageName = getCurrentPackageName()
    if (!scriptContent.trim()) {
      setScriptContent(createDefaultScreenScript(packageName))
    }
  }

  const updateScriptContent = (value: string) => {
    setScriptContent(value)
  }

  const openScriptPicker = async () => {
    if (debugTaskActive) {
      message.warning('调试任务正在运行，请先停止调试')
      return
    }

    setScriptPickerOpen(true)
    setScriptPickerLoading(true)
    try {
      const response = await scriptApi.getList()
      setSavedScripts(response.data.items || [])
    } catch (error) {
      console.error('Failed to fetch saved scripts:', error)
      message.error('获取已保存脚本失败')
    } finally {
      setScriptPickerLoading(false)
    }
  }

  const selectSavedScript = (script: Script) => {
    setScriptContent(script.content)
    setScriptName(script.name)
    setScriptDescription(script.description || '')
    setScriptTags(script.tags || [])
    setLoadedScript(script)
    setDebugCurrentLine(null)
    setDebugScriptSnapshot('')
    setScriptPickerOpen(false)
    setActiveWorkspaceTab('script')
    message.success('已载入脚本')
  }

  const createExampleScript = () => {
    setScriptContent(createDefaultScreenScript(getCurrentPackageName()))
    setScriptName('')
    setScriptDescription('')
    setScriptTags(['screen-debug'])
    setLoadedScript(null)
    setDebugCurrentLine(null)
    setDebugScriptSnapshot('')
    setDebugScriptId(null)
    setScriptPickerOpen(false)
    setActiveWorkspaceTab('script')
    message.success('已新建脚本')
  }

  const activateScriptWriter = () => {
    ensureScriptDraft()
    setActiveWorkspaceTab('script')
  }

  const appendScriptSnippet = (snippet: LocatorSnippet) => {
    ensureScriptDraft()
    const packageName = getCurrentPackageName()
    setScriptContent((current) => {
      const base = (current.trim() ? current : createDefaultScreenScript(packageName)).trimEnd()
      return `${base}${base ? '\n\n' : ''}${snippet.code}\n`
    })
    setActiveWorkspaceTab('script')
    message.success('已插入脚本')
  }

  const openSaveScriptModal = () => {
    if (!scriptContent.trim()) {
      message.warning('请填写脚本内容')
      return
    }
    if (!scriptName.trim()) {
      setScriptName(getDefaultScriptName())
    }
    if (!scriptDescription.trim()) {
      setScriptDescription('从投屏页编写并保存的自动化脚本')
    }
    setScriptSaveModalOpen(true)
  }

  const saveScript = async () => {
    if (!scriptName.trim()) {
      message.warning('请填写脚本名称')
      return
    }
    if (!scriptContent.trim()) {
      message.warning('请填写脚本内容')
      return
    }

    setScriptSaving(true)
    try {
      const validation = await scriptApi.validate(scriptContent)
      if (!validation.data.valid) {
        message.error(validation.data.errors[0] || '脚本校验失败')
        return
      }
      if (validation.data.warnings.length > 0) {
        message.warning(validation.data.warnings[0])
      }

      const scriptData = {
        name: scriptName.trim(),
        description: scriptDescription.trim(),
        script_type: 'python',
        content: scriptContent,
        status: loadedScript?.status || 'draft',
        tags: scriptTags,
      } as const

      const response = loadedScript
        ? await scriptApi.update(loadedScript.id, scriptData)
        : await scriptApi.create(scriptData)

      setLoadedScript(response.data)
      message.success(loadedScript ? '脚本已更新' : '脚本已保存到脚本管理')
      setScriptSaveModalOpen(false)
    } catch (error) {
      console.error('Failed to save script from screen page:', error)
      message.error('保存脚本失败')
    } finally {
      setScriptSaving(false)
    }
  }

  const saveDebugDraft = async (): Promise<Script> => {
    const debugTags = buildDebugTags(scriptTags)
    const data = {
      name: `${currentDevice?.name || selectedDevice || '投屏'} 调试脚本`,
      description: '投屏页自动保存的调试脚本草稿',
      script_type: 'python' as const,
      content: scriptContent,
      status: 'draft' as const,
      tags: debugTags,
    }

    if (debugScriptId) {
      try {
        const response = await scriptApi.update(debugScriptId, data)
        return response.data
      } catch (error) {
        console.warn('Failed to update debug draft, creating a new one:', error)
        setDebugScriptId(null)
      }
    }

    const response = await scriptApi.create(data)
    setDebugScriptId(response.data.id)
    return response.data
  }

  const runDebugScript = async () => {
    if (debugTaskActive) {
      message.warning('调试任务正在运行，请先停止调试')
      return
    }
    if (!scriptContent.trim()) {
      message.warning('请填写脚本内容')
      return
    }
    if (!selectedDevice) {
      message.warning('请先选择设备')
      return
    }
    if (!currentDevice || currentDevice.status !== 'online') {
      message.warning('当前设备不在线或已被占用，无法运行调试')
      return
    }

    setDebugSubmitting(true)
    try {
      const validation = await scriptApi.validate(scriptContent)
      if (!validation.data.valid) {
        message.error(validation.data.errors[0] || '脚本校验失败')
        return
      }
      if (validation.data.warnings.length > 0) {
        message.warning(validation.data.warnings[0])
      }

      const debugScript = await saveDebugDraft()
      const debugPlatform = currentDevice.os.toLowerCase() === 'ios' ? 'ios' : 'android'
      if (debugPlatform === 'ios') {
        const released = await releaseDebugSession(selectedDevice)
        if (!released) {
          throw new Error('释放 iOS 静态调试 session 失败，请稍后重试')
        }
        setStaticDebugSessionActive(false)
      }
      const response = await taskApi.create({
        script_id: debugScript.id,
        device_id: selectedDevice,
        device_platform: debugPlatform,
        device_capabilities: {
          automationName: debugPlatform === 'ios' ? 'XCUITest' : 'UiAutomator2',
          noReset: true,
        },
        parameters: {
          debug_trace_lines: true,
        },
      })

      setDebugTask(response.data)
      setDebugTaskLogs([])
      setDebugCurrentLine(null)
      setDebugScriptSnapshot(scriptContent)
      message.success('调试任务已创建')
    } catch (error) {
      console.error('Failed to run debug script:', error)
      const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
      message.error(detail || '调试任务创建失败，请确认设备在线且未被占用')
    } finally {
      setDebugSubmitting(false)
    }
  }

  const cancelDebugTask = async () => {
    if (!debugTask) return

    setDebugCanceling(true)
    try {
      await taskApi.cancel(debugTask.id)
      const [taskResponse, logsResponse] = await Promise.all([
        taskApi.getDetail(debugTask.id).catch(() => ({ data: { ...debugTask, status: 'cancelled' as const } })),
        taskApi.getLogs(debugTask.id, { limit: 1000 }),
      ])
      setDebugTask(taskResponse.data)
      applyDebugLogs(logsResponse.data)
      message.success('调试任务已取消')
    } catch (error) {
      console.error('Failed to cancel debug task:', error)
      message.error('调试任务取消失败')
    } finally {
      setDebugCanceling(false)
    }
  }

  // Fullscreen
  const handleFullscreen = () => {
    if (playerContainerRef.current) {
      playerContainerRef.current.requestFullscreen()
    }
  }

  return (
    <div className="screen-page">
      <div className="screen-workbench">
        <DeviceStagePanel
          deviceTitle={currentDevice?.name || selectedDevice || '未选择设备'}
          deviceOsLabel={currentDevice ? formatDeviceOs(currentDevice) : ''}
          hasCurrentDevice={Boolean(currentDevice)}
          statusDotClassName={statusDotClassName}
          statusLabel={isIosStaticDebug ? '静态预览' : hasStartupError ? '连接失败' : hasVideoFrame ? '连接成功' : '连接中'}
          isPlaying={isPlaying}
          loading={loading}
          selectedDevice={selectedDevice}
          screenMirrorSupported={screenMirrorSupported}
          onToggleSession={() => isPlaying ? stopSession() : startSession()}
          playerViewportRef={playerViewportRef}
          playerContainerRef={playerContainerRef}
          playerBoxSize={playerBoxSize}
          isIosStaticDebug={isIosStaticDebug}
          isIosDirectMjpegMirror={isIosDirectMjpegMirror}
          iosMjpegStreamUrl={iosMjpegStreamUrl}
          deviceInfo={deviceInfo}
          handleTouchInput={handleTouchInput}
          uiElements={uiElements}
          visibleUiElements={visibleUiElements}
          selectedUiElement={selectedUiElement}
          onSelectUiElement={setSelectedUiElement}
          renderMetrics={renderMetrics}
          uiScreen={uiScreen}
          lkSession={lkSession}
          isInitializing={isInitializing}
          startupStatusText={startupStatusText}
          onIOSMJPEGLoad={() => {
            setHasVideoFrame(true)
            setLoading(false)
            setSessionDiagnostics((current) => current && { ...current, last_error: undefined })
            if (startRequestedAtRef.current !== null) {
              setBrowserFirstFrameMs(Math.round(performance.now() - startRequestedAtRef.current))
            }
          }}
          onIOSMJPEGError={() => {
            if (selectedDevice) {
              void requestStopIOSMJPEG(selectedDevice)
            }
            setHasVideoFrame(false)
            setLoading(false)
            setIsPlaying(false)
            setMjpegStreamKey(0)
            activeSessionDeviceRef.current = null
            activeSessionKindRef.current = null
            setSessionDiagnostics({
              active: false,
              stage: 'error',
              stage_label: 'iOS MJPEG direct error',
              last_error: 'iOS MJPEG 直连流加载失败',
            })
          }}
          onConnectionStateChange={handleConnectionStateChange}
          onWebRTCStats={handleWebRTCStats}
          onWebRTCFirstFrame={() => {
            setHasVideoFrame(true)
            setLoading(false)
            if (startRequestedAtRef.current !== null) {
              setBrowserFirstFrameMs(Math.round(performance.now() - startRequestedAtRef.current))
            }
          }}
          onRoomCreated={(room) => { lkRoomRef.current = room }}
          iosTapMode={iosTapMode}
          iosSwipeMode={iosSwipeMode}
          onStaticStageClick={handleStaticStageClick}
          onStaticStagePointerDown={handleStaticStagePointerDown}
          onStaticStagePointerMove={handleStaticStagePointerMove}
          onStaticStagePointerUp={handleStaticStagePointerUp}
          onStaticStagePointerCancel={handleStaticStagePointerCancel}
          staticScreenshot={staticScreenshot}
          staticScreenshotLoading={staticScreenshotLoading}
          staticActionLoading={staticActionLoading}
          remoteControlSupported={remoteControlSupported}
          onSendKey={sendKey}
          onFullscreen={handleFullscreen}
          virtualKeyboardOpen={virtualKeyboardOpen}
          onVirtualKeyboardOpenChange={setVirtualKeyboardOpen}
          quickInputText={quickInputText}
          onQuickInputTextChange={setQuickInputText}
          onSendText={() => { void sendText() }}
          onClearStaticText={() => { void clearStaticText() }}
          isIosTextInputAvailable={isIosTextInputAvailable}
          isIosStaticActionSupported={isIosStaticActionSupported}
          iosModeLabel={iosModeLabel}
          staticAutoRefresh={staticAutoRefresh}
          staticAutoRefreshIntervalMs={staticAutoRefreshIntervalMs}
          staticRefreshDurationMs={staticRefreshDurationMs}
          staticRefreshFailures={staticRefreshFailures}
          staticDebugSessionActive={staticDebugSessionActive}
          staticPointerPoint={staticPointerPoint}
          lastStaticAction={lastStaticAction}
          staticRefreshLastError={staticRefreshLastError}
          fps={fps}
          networkLatencyMs={networkLatencyMs}
          browserFirstFrameMs={browserFirstFrameMs}
          lastIosControlStatus={lastIosControlStatus}
        />

        <section className="screen-workspace">
          <div className="workspace-tabs">
            <button
              type="button"
              className={`workspace-tab ${activeWorkspaceTab === 'inspect' ? 'active' : ''}`}
              onClick={() => setActiveWorkspaceTab('inspect')}
            >
              控件检查
            </button>
            <button
              type="button"
              className={`workspace-tab ${activeWorkspaceTab === 'script' ? 'active' : ''}`}
              onClick={activateScriptWriter}
            >
              编写脚本
            </button>
            <button
              type="button"
              className={`workspace-tab ${activeWorkspaceTab === 'logcat' ? 'active' : ''}`}
              onClick={() => setActiveWorkspaceTab('logcat')}
            >
              Logcat
            </button>
          </div>

          {activeWorkspaceTab === 'inspect' && (
            <InspectorPanel
              selectedDevice={selectedDevice}
              inspectReady={inspectReady}
              uiHierarchySupported={uiHierarchySupported}
              loadingUiHierarchy={loadingUiHierarchy}
              onFetchUiHierarchy={fetchUiHierarchy}
              isIosStaticDebug={isIosStaticDebug}
              screenshotSupported={screenshotSupported}
              staticScreenshotLoading={staticScreenshotLoading}
              onRefreshScreenshot={() => refreshStaticScreenshot(false)}
              staticAutoRefresh={staticAutoRefresh}
              staticAutoRefreshIntervalMs={staticAutoRefreshIntervalMs}
              staticScreenshot={staticScreenshot}
              staticActionLoading={staticActionLoading}
              onStaticAutoRefreshChange={setStaticAutoRefresh}
              onStaticAutoRefreshIntervalChange={setStaticAutoRefreshIntervalMs}
              isIosStaticActionSupported={isIosStaticActionSupported}
              iosTapMode={iosTapMode}
              iosSwipeMode={iosSwipeMode}
              onIosTapModeChange={(checked) => {
                setIosTapMode(checked)
                if (checked) setIosSwipeMode(false)
              }}
              onIosSwipeModeChange={(checked) => {
                setIosSwipeMode(checked)
                if (checked) setIosTapMode(false)
              }}
              selectedUiElement={selectedUiElement}
              uiElements={uiElements}
              onTapSelectedUiElement={tapSelectedUiElement}
              onLongPressSelectedUiElement={longPressSelectedUiElement}
              onClearUiHierarchy={clearUiHierarchy}
              currentDeviceLabel={currentDevice?.name || selectedDevice || '-'}
            />
          )}

          {activeWorkspaceTab === 'script' && (
            <ScriptWorkspacePanel
              debugTaskActive={debugTaskActive}
              debugCanceling={debugCanceling}
              debugSubmitting={debugSubmitting}
              onOpenScriptPicker={openScriptPicker}
              onCancelDebugTask={cancelDebugTask}
              onRunDebugScript={runDebugScript}
              onOpenSaveScriptModal={openSaveScriptModal}
              scriptContent={scriptContent}
              onScriptContentChange={updateScriptContent}
              activeDebugLine={activeDebugLine}
              failedDebugLine={failedDebugLine}
              scriptLineCount={scriptLineCount}
              debugTask={debugTask}
              visibleDebugLogs={visibleDebugLogs}
              debugScreenshots={debugScreenshots}
              selectedUiElement={selectedUiElement}
              locatorSnippets={locatorSnippets}
              onAppendScriptSnippet={appendScriptSnippet}
            />
          )}

          {activeWorkspaceTab === 'logcat' && (
            <div className="workspace-panel logcat-panel">
              <div className="workspace-toolbar compact">
                <Text strong>Logcat</Text>
              </div>
              <div className="logcat-placeholder">
                <Text type="secondary">Logcat 能力待接入。</Text>
              </div>
            </div>
          )}
        </section>
      </div>

      <ScriptModals
        pickerOpen={scriptPickerOpen}
        pickerLoading={scriptPickerLoading}
        savedScripts={savedScripts}
        onClosePicker={() => setScriptPickerOpen(false)}
        onCreateExampleScript={createExampleScript}
        onSelectSavedScript={selectSavedScript}
        saveOpen={scriptSaveModalOpen}
        saving={scriptSaving}
        scriptName={scriptName}
        scriptTags={scriptTags}
        scriptDescription={scriptDescription}
        onScriptNameChange={setScriptName}
        onScriptTagsChange={setScriptTags}
        onScriptDescriptionChange={setScriptDescription}
        onSaveScript={saveScript}
        onCloseSave={() => setScriptSaveModalOpen(false)}
      />
    </div>
  )
}
