import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { message } from 'antd'
import type { Device, Script, Task, TaskLogEntry } from '@/types'
import { scriptApi, taskApi } from '@/services/api'
import { formatDeviceOs, mapDevice } from '@/utils/device'
import type {
  LocatorSnippet,
  RenderMetrics,
  UIElementNode,
  WorkspaceTab,
} from './types'
import { buildLocatorSnippets, buildVisibleUiElements } from './uiHierarchy'
import {
  IOS_DIRECT_MJPEG_SCREEN_DRIVERS,
  KEYBOARD_KEY_CODE_MAP,
  fetchDeviceScreenInfo,
  fetchDevicesPayload,
  fetchUIHierarchy,
  releaseDebugSession,
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
import WorkspacePanel from './WorkspacePanel'
import ScriptModals from './ScriptModals'
import useIosDebugActions from './useIosDebugActions'
import useScreenSession from './useScreenSession'
import './ScreenPage.css'

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
  const [uiElements, setUiElements] = useState<UIElementNode[]>([])
  const [selectedUiElement, setSelectedUiElement] = useState<UIElementNode | null>(null)
  const [loadingUiHierarchy, setLoadingUiHierarchy] = useState(false)
  const [playerBoxSize, setPlayerBoxSize] = useState<{ width: number; height: number } | null>(null)
  const [renderMetrics, setRenderMetrics] = useState<RenderMetrics | null>(null)
  const [uiScreen, setUiScreen] = useState<{ width: number; height: number } | null>(null)
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
  const iosModeLabel = isIosDirectMjpegMirror
    ? 'iOS MJPEG 直连预览'
    : 'iOS 静态预览'
  
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

  const clearUiHierarchy = useCallback(() => {
    setUiElements([])
    setSelectedUiElement(null)
    setUiScreen(null)
  }, [])

  const {
    staticScreenshot,
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
    lastStaticAction,
    lastIosControlStatus,
    refreshStaticScreenshot,
    handleTouchInput: handleIosTouchInput,
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
  } = useIosDebugActions({
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
  })

  const handleStopSessionCleanup = useCallback(() => {
    clearUiHierarchy()
    resetStaticDebugState()
  }, [clearUiHierarchy, resetStaticDebugState])

  const {
    isPlaying,
    loading,
    fps,
    hasVideoFrame,
    browserFirstFrameMs,
    networkLatencyMs,
    lkSession,
    iosMjpegStreamUrl,
    hasStartupError,
    isInitializing,
    statusDotClassName,
    startSession,
    stopSession,
    publishControl,
    sendAndroidKey,
    flushPendingMove,
    scheduleMove,
    handleConnectionStateChange,
    handleWebRTCStats,
    handleIOSMJPEGLoad,
    handleIOSMJPEGError,
    handleWebRTCFirstFrame,
    handleRoomCreated,
  } = useScreenSession({
    selectedDevice,
    devicesLoaded,
    currentDevice,
    isIosDevice,
    isIosLivePreview,
    isIosStaticDebug,
    isIosDirectMjpegMirror,
    remoteControlSupported,
    onIosLogicalScreen: applyIosLogicalScreen,
    onVideoScreen: setDeviceInfo,
    onStopCleanup: handleStopSessionCleanup,
  })

  const handleTouchInput = useCallback((type: string, x: number, y: number, extra?: Record<string, unknown>) => {
    if (handleIosTouchInput(type, x, y, extra)) return
    if (!remoteControlSupported) return
    if (type !== 'touch') return
    const action = extra?.action || 'move'
    if (action === 'move') {
      scheduleMove(x, y)
      return
    }

    flushPendingMove()
    publishControl({ type: 'touch', action, x, y }, true)
  }, [flushPendingMove, handleIosTouchInput, publishControl, remoteControlSupported, scheduleMove])

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
  }, [currentDevice, isIosDevice, isIosDirectMjpegMirror, isIosStaticDebug, isPlaying, refreshStaticScreenshot, selectedDevice, setStaticDebugSessionActive])

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
  const isIosTextInputAvailable = Boolean(isIosStaticActionSupported && (isIosStaticDebug || isPlaying))
  const startupStatusText = '正在初始化设备，请稍后...'

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
      const success = await sendIosText(text)
      if (success) {
        setQuickInputText('')
        setVirtualKeyboardOpen(false)
      }
      return
    }

    if (!remoteControlSupported) return

    publishControl({ type: 'text', text }, true)
    setQuickInputText('')
    setVirtualKeyboardOpen(false)
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
          onIOSMJPEGLoad={handleIOSMJPEGLoad}
          onIOSMJPEGError={handleIOSMJPEGError}
          onConnectionStateChange={handleConnectionStateChange}
          onWebRTCStats={handleWebRTCStats}
          onWebRTCFirstFrame={handleWebRTCFirstFrame}
          onRoomCreated={handleRoomCreated}
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

        <WorkspacePanel
          activeWorkspaceTab={activeWorkspaceTab}
          onOpenInspect={() => setActiveWorkspaceTab('inspect')}
          onOpenScript={activateScriptWriter}
          onOpenLogcat={() => setActiveWorkspaceTab('logcat')}
          selectedDevice={selectedDevice}
          inspectReady={inspectReady}
          uiHierarchySupported={uiHierarchySupported}
          loadingUiHierarchy={loadingUiHierarchy}
          onFetchUiHierarchy={fetchUiHierarchy}
          isIosStaticDebug={isIosStaticDebug}
          screenshotSupported={screenshotSupported}
          staticScreenshotLoading={staticScreenshotLoading}
          onRefreshScreenshot={() => { void refreshStaticScreenshot(false) }}
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
          locatorSnippets={locatorSnippets}
          onAppendScriptSnippet={appendScriptSnippet}
        />
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
