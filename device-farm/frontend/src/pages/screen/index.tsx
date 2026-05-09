import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Alert, Button, Form, Image, Input, List, Modal, Popover, Select, Space, Table, Tag, Typography, message } from 'antd'
import PlayCircleOutlined from '@ant-design/icons/PlayCircleOutlined'
import PauseCircleOutlined from '@ant-design/icons/PauseCircleOutlined'
import FullscreenOutlined from '@ant-design/icons/FullscreenOutlined'
import VideoCameraOutlined from '@ant-design/icons/VideoCameraOutlined'
import HomeOutlined from '@ant-design/icons/HomeOutlined'
import RollbackOutlined from '@ant-design/icons/RollbackOutlined'
import AppstoreOutlined from '@ant-design/icons/AppstoreOutlined'
import KeyOutlined from '@ant-design/icons/KeyOutlined'
import SendOutlined from '@ant-design/icons/SendOutlined'
import DeleteOutlined from '@ant-design/icons/DeleteOutlined'
import PlusOutlined from '@ant-design/icons/PlusOutlined'
import ReloadOutlined from '@ant-design/icons/ReloadOutlined'
import { Room } from 'livekit-client'
import type { Device, Script, Task, TaskLogEntry } from '@/types'
import WebrtcPlayer from '@/components/WebrtcPlayer'
import { TouchOverlay } from '@/components/TouchHandler'
import CodeEditor from '@/components/CodeEditor'
import { scriptApi, taskApi } from '@/services/api'
import { formatDeviceOs, mapDevice } from '@/utils/device'
import './ScreenPage.css'

const { Text } = Typography

const taskStatusColors: Record<Task['status'], string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
  cancelled: 'warning',
}

const taskStatusText: Record<Task['status'], string> = {
  pending: '排队中',
  running: '运行中',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
}

const SCREEN_HTTP_URL = import.meta.env.VITE_SCREEN_HTTP_URL || ''
const TOUCH_MOVE_INTERVAL_MS = 16
const KEYBOARD_KEY_CODE_MAP: Record<string, number> = {
  Backspace: 67,
  Enter: 66,
  Tab: 61,
  Escape: 111,
  Delete: 112,
  ArrowUp: 19,
  ArrowDown: 20,
  ArrowLeft: 21,
  ArrowRight: 22,
}

function requestStopSession(deviceId: string) {
  void fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${encodeURIComponent(deviceId)}/stop`, {
    method: 'POST',
    credentials: 'include',
    keepalive: true,
  }).catch((error) => {
    console.error('Failed to stop session:', error)
  })
}

async function releaseDebugSession(deviceId: string, keepalive = false) {
  const res = await fetch(`/api/v1/devices/${encodeURIComponent(deviceId)}/debug-session`, {
    method: 'DELETE',
    credentials: 'include',
    keepalive,
  })
  return res.ok
}

function requestReleaseDebugSession(deviceId: string) {
  void releaseDebugSession(deviceId, true).catch((error) => {
    console.error('Failed to release debug session:', error)
  })
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false
  const tagName = target.tagName.toLowerCase()
  return tagName === 'input' || tagName === 'textarea' || target.isContentEditable
}

interface UIElementBounds {
  x: number
  y: number
  width: number
  height: number
}

interface UISelectorSuggestion {
  type: string
  value: string
}

interface UIElementNode {
  uid: string
  parent_uid?: string | null
  depth: number
  index: number
  class_name: string
  resource_id: string
  text: string
  content_desc: string
  package: string
  bounds: UIElementBounds
  center: { x: number; y: number }
  clickable: boolean
  enabled: boolean
  selected: boolean
  focused: boolean
  scrollable: boolean
  xpath: string
  selector_suggestions: UISelectorSuggestion[]
  attributes?: Record<string, unknown>
}

interface UIHierarchyResponse {
  device_id: string
  platform: string
  captured_at: string
  screen: { width: number; height: number }
  elements: UIElementNode[]
}

interface RenderMetrics {
  left: number
  top: number
  width: number
  height: number
}

interface ScreenSessionDiagnostics {
  active?: boolean
  stage?: string
  stage_label?: string
  durations_ms?: Record<string, number>
  frame_count?: number
  key_frame_count?: number
  last_error?: string
  reused?: boolean
}

interface LocatorSnippet {
  key: string
  title: string
  description: string
  code: string
}

type WorkspaceTab = 'inspect' | 'script' | 'logcat'

function pythonString(value: string) {
  return JSON.stringify(value)
}

function createDefaultScreenScript(packageName = 'com.example.app') {
  return `# 平台脚本示例：统一使用 app.xxx 调用平台能力
# 创建任务时只需要选择设备，启动哪个 App 由脚本自己控制
package = ${pythonString(packageName || 'com.example.app')}

app.log("script start")

# 启动或拉起 App
app.activate_app(package)
app.wait(5)

# 截图会自动上传到任务详情
app.screenshot()

# 常见弹窗处理
if app.has_text("同意"):
    app.click_text("同意", timeout=5)
    app.wait(2)
    app.screenshot()

if app.has_text("允许"):
    app.click_text("允许", timeout=5)
    app.wait(1)

# 页面断言
source = app.source()
assert_true(len(source) > 0, "页面源码为空，App 可能未正常启动")

# 退出 App，也可以使用 app.restart_app(package) 验证重启
app.terminate_app(package)

app.log("script passed")
test_pass()
`
}

function findSelector(element: UIElementNode, type: string) {
  return element.selector_suggestions.find((selector) => selector.type === type)?.value || ''
}

function buildLocatorSnippets(element: UIElementNode | null, platform = 'android'): LocatorSnippet[] {
  if (!element) return []

  const snippets: LocatorSnippet[] = []
  if (platform === 'ios') {
    const accessibilityId = findSelector(element, 'accessibility_id') || element.content_desc
    const predicate = findSelector(element, 'ios_predicate')
    const classChain = findSelector(element, 'ios_class_chain')

    if (accessibilityId) {
      snippets.push({
        key: 'ios-click-accessibility',
        title: '按 accessibility-id 点击',
        description: '推荐用于 iOS 上稳定的 name 或 accessibility label。',
        code: `app.click(AppiumBy.ACCESSIBILITY_ID, ${pythonString(accessibilityId)}, timeout=10)`,
      })
    }
    if (predicate) {
      snippets.push({
        key: 'ios-click-predicate',
        title: '按 iOS Predicate 点击',
        description: '适合用 name、label 或 value 精确定位。',
        code: `app.click(AppiumBy.IOS_PREDICATE, ${pythonString(predicate)}, timeout=10)`,
      })
    }
    if (classChain) {
      snippets.push({
        key: 'ios-click-class-chain',
        title: '按 iOS Class Chain 点击',
        description: '适合没有稳定 accessibility id 时缩小控件类型范围。',
        code: `app.click(AppiumBy.IOS_CLASS_CHAIN, ${pythonString(classChain)}, timeout=10)`,
      })
    }
    if (element.text) {
      snippets.push({
        key: 'ios-assert-text',
        title: '断言文本存在',
        description: 'iOS 会按 label、name、value 查询文本。',
        code: `app.assert_text(${pythonString(element.text)})`,
      })
    }
    if (element.xpath) {
      snippets.push({
        key: 'ios-click-xpath',
        title: '按 XPath 点击',
        description: '结构变化时需要维护，建议作为兜底。',
        code: `app.click(AppiumBy.XPATH, ${pythonString(element.xpath)}, timeout=10)`,
      })
    }
    snippets.push({
      key: 'ios-tap-coordinate',
      title: '按坐标点击',
      description: '兜底方案，分辨率或布局变化时稳定性较弱。',
      code: `app.tap(${Math.round(element.center.x)}, ${Math.round(element.center.y)})`,
    })
    return snippets
  }

  if (element.resource_id) {
    snippets.push({
      key: 'click-id',
      title: '按 resource-id 点击',
      description: '推荐用于稳定控件，优先级最高。',
      code: `app.click(AppiumBy.ID, ${pythonString(element.resource_id)}, timeout=10)`,
    })
    snippets.push({
      key: 'get-text-id',
      title: '按 resource-id 读取文本',
      description: '适合断言标题、按钮文案或输入框内容。',
      code: `text = app.get_text(AppiumBy.ID, ${pythonString(element.resource_id)}, timeout=10)\napp.log(f"element text: {text}")`,
    })
  }

  if (element.content_desc) {
    snippets.push({
      key: 'click-accessibility',
      title: '按 accessibility-id 点击',
      description: '适合有 content-desc 的图标按钮。',
      code: `app.click(AppiumBy.ACCESSIBILITY_ID, ${pythonString(element.content_desc)}, timeout=10)`,
    })
  }

  if (element.text) {
    if (element.clickable) {
      snippets.push({
        key: 'click-text',
        title: '按文本点击',
        description: '适合弹窗按钮、菜单项等短文本控件。',
        code: `app.click_text(${pythonString(element.text)}, timeout=5)`,
      })
    }
    snippets.push({
      key: 'assert-text',
      title: '断言文本存在',
      description: element.clickable ? '适合验证页面是否进入预期状态。' : '当前控件不可点击，建议用于断言；点击请优先选择可点击父级控件。',
      code: `app.assert_text(${pythonString(element.text)})`,
    })
  }

  if (element.xpath) {
    snippets.push({
      key: 'click-xpath',
      title: '按 XPath 点击',
      description: '当没有稳定 ID 时使用，页面结构变化时需要维护。',
      code: `app.click(AppiumBy.XPATH, ${pythonString(element.xpath)}, timeout=10)`,
    })
  }

  snippets.push({
    key: 'tap-coordinate',
    title: '按坐标点击',
    description: '兜底方案，分辨率或布局变化时稳定性较弱。',
    code: `app.tap(${Math.round(element.center.x)}, ${Math.round(element.center.y)})`,
  })

  return snippets
}

const isActiveTask = (task?: Task | null) => Boolean(task && ['pending', 'running'].includes(task.status))

const formatDateTime = (value?: string) => value ? new Date(value).toLocaleString() : '-'

const formatDuration = (task?: Task | null) => {
  if (!task) return '-'
  if (typeof task.result?.duration === 'number') {
    return `${task.result.duration.toFixed(2)}s`
  }
  if (task.started_at && task.finished_at) {
    const duration = (new Date(task.finished_at).getTime() - new Date(task.started_at).getTime()) / 1000
    return `${duration.toFixed(2)}s`
  }
  return '-'
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
  const currentDevice = devices.find((d) => d.id === selectedDevice)
  const screenMirrorSupported = currentDevice?.capabilities.screenMirror ?? false
  const remoteControlSupported = currentDevice?.capabilities.remoteControl ?? false
  const uiHierarchySupported = currentDevice?.capabilities.uiHierarchy ?? false
  const screenshotSupported = currentDevice?.capabilities.screenshot ?? false
  const isIosStaticDebug = Boolean(
    currentDevice
    && currentDevice.os.toLowerCase() === 'ios'
    && !screenMirrorSupported
    && uiHierarchySupported
    && screenshotSupported
  )
  
  // LiveKit state
  const [lkSession, setLkSession] = useState<{ url: string; token: string } | null>(null)
  const lkRoomRef = useRef<Room | null>(null)
  const pendingMoveRef = useRef<{ x: number; y: number } | null>(null)
  const moveTimerRef = useRef<number | null>(null)
  const autoStartedDeviceRef = useRef<string | null>(null)
  const autoStartBlockedRef = useRef<string | null>(null)
  const startRequestedAtRef = useRef<number | null>(null)
  const activeSessionDeviceRef = useRef<string | null>(null)

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
        const res = await fetch('/api/v1/devices')
        const data = await res.json()
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
        const res = await fetch(`/api/v1/devices/${selectedDevice}`)
        const data = await res.json()
        const resolution = data.screen_resolution || data.screenResolution || '1080x1920'
        const [width, height] = resolution.split('x').map(Number)
        setDeviceInfo({ width: width || 1080, height: height || 1920 })
      } catch {
        setDeviceInfo({ width: 1080, height: 1920 })
      }
    }
    fetchDeviceInfo()
  }, [selectedDevice])

  // Start session on backend
  const startSession = useCallback(async () => {
    if (!selectedDevice) return
    if (devicesLoaded && !currentDevice) {
      message.error('未找到当前设备，请回到设备列表重新选择')
      return
    }
    if (currentDevice?.status === 'offline') {
      message.error('当前设备离线，无法投屏')
      return
    }
    if (currentDevice && !currentDevice.capabilities.screenMirror) {
      message.error('当前设备连接不支持投屏')
      return
    }
    setLoading(true)
    setSessionDiagnostics(null)
    setBrowserFirstFrameMs(null)
    setNetworkLatencyMs(null)
    startRequestedAtRef.current = performance.now()
    try {
      const res = await fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${selectedDevice}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
      })
      const data = await res.json()
      if (res.ok && data.token) {
        const videoWidth = Number(data.video_width || data.videoWidth)
        const videoHeight = Number(data.video_height || data.videoHeight)
        if (videoWidth > 0 && videoHeight > 0) {
          setDeviceInfo({ width: videoWidth, height: videoHeight })
        }
        setHasVideoFrame(false)
        setSessionDiagnostics(data as ScreenSessionDiagnostics)
        activeSessionDeviceRef.current = selectedDevice
        setLkSession({ url: data.livekit_url || 'ws://localhost:7880', token: data.token })
        setIsPlaying(true)
      } else {
        message.error(data.error || '无法获取连接 Token')
      }
    } catch (e) {
      message.error('启动会话失败')
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [currentDevice, devicesLoaded, selectedDevice])

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
    if (currentDevice.status === 'offline') {
      setLoading(false)
      const blockKey = `${selectedDevice}:offline`
      if (autoStartBlockedRef.current !== blockKey) {
        autoStartBlockedRef.current = blockKey
        message.error('当前设备离线，无法投屏')
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

    autoStartBlockedRef.current = null
    autoStartedDeviceRef.current = selectedDevice
    void startSession()
  }, [currentDevice, devicesLoaded, isIosStaticDebug, isPlaying, lkSession, selectedDevice, startSession])

  const stopSession = async () => {
    if (!selectedDevice) return
    setIsPlaying(false)
    setLkSession(null)
    setHasVideoFrame(false)
    setSessionDiagnostics(null)
    setBrowserFirstFrameMs(null)
    setNetworkLatencyMs(null)
    startRequestedAtRef.current = null
    activeSessionDeviceRef.current = null
    clearUiHierarchy()
    setStaticScreenshot(null)
    flushPendingMove()
    lkRoomRef.current = null
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

  // Handle touch input via DataChannel
  const handleTouchInput = useCallback(
    (type: string, x: number, y: number, extra?: Record<string, unknown>) => {
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
    [flushPendingMove, publishControl, remoteControlSupported, scheduleMove]
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

  const refreshStaticScreenshot = useCallback(async (silent = false, timeoutMs = 18000) => {
    if (!selectedDevice || !isIosStaticDebug) return false
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)
    setStaticScreenshotLoading(true)
    try {
      const res = await fetch(`/api/v1/devices/${selectedDevice}/screenshot`, {
        credentials: 'include',
        signal: controller.signal,
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || '刷新截图失败')
      }
      if (!data.image) {
        throw new Error('截图数据为空')
      }
      setStaticScreenshot(`data:image/${data.format || 'png'};base64,${data.image}`)
      if (!silent) {
        message.success('截图已刷新')
      }
      return true
    } catch (e) {
      const error = e as Error
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
    const timeoutId = window.setTimeout(() => controller.abort(), 18000)
    try {
      if (isIosStaticDebug) {
        const screenshotOk = await refreshStaticScreenshot(true)
        if (!screenshotOk) {
          message.warning('截图刷新失败，但会继续尝试获取控件树')
        }
      }
      const res = await fetch(`/api/v1/devices/${selectedDevice}/ui-hierarchy`, {
        credentials: 'include',
        signal: controller.signal,
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || '获取控件失败')
      }

      const result = data as UIHierarchyResponse
      setUiElements(result.elements || [])
      setSelectedUiElement(null)
      if (result.screen?.width > 0 && result.screen?.height > 0) {
        setUiScreen({ width: result.screen.width, height: result.screen.height })
        if (isIosStaticDebug) {
          setDeviceInfo({ width: result.screen.width, height: result.screen.height })
        }
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
  }, [currentDevice, isIosStaticDebug, isPlaying, refreshStaticScreenshot, selectedDevice])

  const handleConnectionStateChange = useCallback((state: string) => {
    if (state === 'disconnected') {
      setHasVideoFrame(false)
    }
    if (state === 'connected') {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!selectedDevice || !isPlaying || hasVideoFrame) return

    let cancelled = false
    const fetchSessionDiagnostics = async () => {
      try {
        const res = await fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${selectedDevice}`, {
          credentials: 'include',
        })
        const data = await res.json()
        if (!cancelled && res.ok) {
          setSessionDiagnostics(data as ScreenSessionDiagnostics)
        }
      } catch (e) {
        console.error('Failed to fetch screen session diagnostics:', e)
      }
    }

    void fetchSessionDiagnostics()
    const interval = window.setInterval(fetchSessionDiagnostics, 1000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [hasVideoFrame, isPlaying, selectedDevice])

  useEffect(() => {
    return () => {
      if (moveTimerRef.current) {
        window.clearTimeout(moveTimerRef.current)
      }
      const activeDevice = activeSessionDeviceRef.current
      if (activeDevice) {
        requestStopSession(activeDevice)
      }
    }
  }, [])

  useEffect(() => {
    setStaticScreenshot(null)
    if (!selectedDevice || !isIosStaticDebug) return
    return () => {
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

  const uiPropertyRows = selectedUiElement
    ? [
        { key: 'uid', property: 'uid', value: selectedUiElement.uid },
        { key: 'class', property: 'class', value: selectedUiElement.class_name },
        { key: 'resource_id', property: 'resource-id', value: selectedUiElement.resource_id },
        { key: 'text', property: 'text', value: selectedUiElement.text },
        { key: 'content_desc', property: 'content-desc', value: selectedUiElement.content_desc },
        { key: 'package', property: 'package', value: selectedUiElement.package },
        {
          key: 'bounds',
          property: 'bounds',
          value: `[${selectedUiElement.bounds.x},${selectedUiElement.bounds.y}][${selectedUiElement.bounds.x + selectedUiElement.bounds.width},${selectedUiElement.bounds.y + selectedUiElement.bounds.height}]`,
        },
        { key: 'center', property: 'center', value: `${selectedUiElement.center.x}, ${selectedUiElement.center.y}` },
        { key: 'clickable', property: 'clickable', value: String(selectedUiElement.clickable) },
        { key: 'enabled', property: 'enabled', value: String(selectedUiElement.enabled) },
        { key: 'selected', property: 'selected', value: String(selectedUiElement.selected) },
        { key: 'focused', property: 'focused', value: String(selectedUiElement.focused) },
        { key: 'scrollable', property: 'scrollable', value: String(selectedUiElement.scrollable) },
        { key: 'xpath', property: 'xpath', value: selectedUiElement.xpath },
        {
          key: 'selectors',
          property: 'selector_suggestions',
          value: selectedUiElement.selector_suggestions.map((s) => `${s.type}: ${s.value}`).join('\n'),
        },
      ]
    : []

  const visibleUiElements = uiElements
    .filter((element) => element.bounds.width > 0 && element.bounds.height > 0)
    .sort((a, b) => b.bounds.width * b.bounds.height - a.bounds.width * a.bounds.height)
  const locatorSnippets = useMemo(
    () => buildLocatorSnippets(selectedUiElement, isIosStaticDebug ? 'ios' : 'android'),
    [isIosStaticDebug, selectedUiElement],
  )
  const scriptLineCount = useMemo(() => scriptContent.split(/\r\n|\r|\n/).length, [scriptContent])
  const visibleDebugLogs = useMemo(
    () => debugTaskLogs.filter((entry) => entry.event_type !== 'script_line'),
    [debugTaskLogs],
  )
  const debugScreenshots = debugTask?.result?.screenshots || []
  const debugTaskActive = isActiveTask(debugTask)
  const debugTaskId = debugTask?.id
  const debugTaskPollingActive = Boolean(debugTask && isActiveTask(debugTask))
  const activeDebugLine = debugScriptSnapshot === scriptContent ? debugCurrentLine : null
  const failedDebugLine = debugTask?.status === 'failed' ? activeDebugLine : null
  const inspectReady = isPlaying || isIosStaticDebug

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
    const latestLineEvent = [...logs]
      .reverse()
      .find((entry) => entry.event_type === 'script_line' && typeof entry.line_number === 'number')
    setDebugCurrentLine(latestLineEvent?.line_number || null)
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

  const sendText = () => {
    const text = quickInputText
    if (!text || !remoteControlSupported) return

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
    const debugTags = Array.from(new Set([...scriptTags, 'screen-debug', 'debug-run']))
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

  const virtualKeyboardContent = (
    <div className="virtual-keyboard-panel">
      <Input.Password
        value={quickInputText}
        onChange={(event) => setQuickInputText(event.target.value)}
        onPressEnter={sendText}
        placeholder="输入文本或密码"
        autoComplete="off"
        disabled={!isPlaying || !remoteControlSupported}
      />
      <Button
        type="primary"
        icon={<SendOutlined />}
        disabled={!quickInputText || !isPlaying || !remoteControlSupported}
        onClick={sendText}
      >
        输入
      </Button>
    </div>
  )

  const uiElementOverlay = uiElements.length > 0 && renderMetrics && uiScreen ? (
    <div
      className="ui-element-layer"
      style={{
        left: renderMetrics.left,
        top: renderMetrics.top,
        width: renderMetrics.width,
        height: renderMetrics.height,
      }}
    >
      {visibleUiElements.map((element) => {
        const isSelected = selectedUiElement?.uid === element.uid
        return (
          <button
            key={element.uid}
            type="button"
            className={`ui-element-box ${isSelected ? 'selected' : ''} ${element.clickable ? 'clickable' : ''}`}
            title={element.resource_id || element.content_desc || element.text || element.class_name}
            style={{
              left: `${(element.bounds.x / uiScreen.width) * 100}%`,
              top: `${(element.bounds.y / uiScreen.height) * 100}%`,
              width: `${(element.bounds.width / uiScreen.width) * 100}%`,
              height: `${(element.bounds.height / uiScreen.height) * 100}%`,
              zIndex: element.depth + 1,
            }}
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              setSelectedUiElement(element)
            }}
          />
        )
      })}
    </div>
  ) : null

  return (
    <div className="screen-page">
      <div className="screen-workbench">
        <section className="device-stage">
          <div className="device-stage-header">
            <div className="device-context">
              <VideoCameraOutlined />
              <span>{currentDevice?.name || selectedDevice || '未选择设备'}</span>
              {currentDevice && <Text type="secondary">{formatDeviceOs(currentDevice)}</Text>}
              <span
                className={`connection-status-dot ${statusDotClassName}`}
                aria-label={isIosStaticDebug ? '静态调试' : hasStartupError ? '连接失败' : hasVideoFrame ? '连接成功' : '连接中'}
                title={isIosStaticDebug ? '静态调试' : hasStartupError ? '连接失败' : hasVideoFrame ? '连接成功' : '连接中'}
              />
            </div>
            <Button
              type={isPlaying ? 'default' : 'primary'}
              icon={isPlaying ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              onClick={() => isPlaying ? stopSession() : startSession()}
              disabled={!selectedDevice || !screenMirrorSupported}
              loading={loading}
            >
              {loading ? '连接中' : isPlaying ? '断开' : '重新连接'}
            </Button>
          </div>

          <div className="device-frame-wrap">
            <div ref={playerViewportRef} className="player-viewport">
              <div
                ref={playerContainerRef}
                className={`player-container ${isPlaying || isIosStaticDebug ? 'active' : ''}`}
                style={playerBoxSize ? { width: playerBoxSize.width, height: playerBoxSize.height } : undefined}
              >
                {isPlaying && lkSession ? (
                  <TouchOverlay
                    screenWidth={deviceInfo?.width || 1080}
                    screenHeight={deviceInfo?.height || 1920}
                    onInput={handleTouchInput}
                    disabled={uiElements.length > 0}
                  >
                    <WebrtcPlayer
                      deviceId={selectedDevice}
                      token={lkSession.token}
                      serverUrl={lkSession.url}
                      waitingText={isInitializing ? startupStatusText : ''}
                      onConnectionStateChange={handleConnectionStateChange}
                      onStats={handleWebRTCStats}
                      onFirstFrame={() => {
                        setHasVideoFrame(true)
                        setLoading(false)
                        if (startRequestedAtRef.current !== null) {
                          setBrowserFirstFrameMs(Math.round(performance.now() - startRequestedAtRef.current))
                        }
                      }}
                      onRoomCreated={(room) => { lkRoomRef.current = room; }}
                    />
                    {isInitializing && (
                      <div className="video-waiting-overlay">
                        <div className="video-waiting-content">
                          <span>{startupStatusText}</span>
                        </div>
                      </div>
                    )}
                    {uiElementOverlay}
                  </TouchOverlay>
                ) : isIosStaticDebug ? (
                  <div className="static-debug-stage">
                    {staticScreenshot ? (
                      <img className="static-debug-screenshot" src={staticScreenshot} alt="iOS static screenshot" />
                    ) : (
                      <div className="player-placeholder static-debug-placeholder">
                        <VideoCameraOutlined style={{ fontSize: 48, marginBottom: 12 }} />
                        <p>iOS 静态调试模式</p>
                        <span>刷新截图或获取控件后查看当前页面</span>
                      </div>
                    )}
                    {staticScreenshotLoading && (
                      <div className="video-waiting-overlay">
                        <div className="video-waiting-content">
                          <span>正在刷新截图...</span>
                        </div>
                      </div>
                    )}
                    {uiElementOverlay}
                  </div>
                ) : (
                  <div className="player-placeholder">
                    <VideoCameraOutlined style={{ fontSize: 56, marginBottom: 16 }} />
                    <p>从设备管理选择设备后点击连接开始投屏</p>
                  </div>
                )}
              </div>
            </div>

            <div className="device-rail">
              <Button shape="circle" icon={<HomeOutlined />} disabled={!remoteControlSupported} onClick={() => sendKey('KEYCODE_HOME')} />
              <Button shape="circle" icon={<RollbackOutlined />} disabled={!remoteControlSupported} onClick={() => sendKey('KEYCODE_BACK')} />
              <Button shape="circle" icon={<AppstoreOutlined />} disabled={!remoteControlSupported} onClick={() => sendKey('KEYCODE_APP_SWITCH')} />
              <Button shape="circle" icon={<FullscreenOutlined />} onClick={handleFullscreen} />
              <Popover
                content={virtualKeyboardContent}
                trigger="click"
                placement="left"
                open={virtualKeyboardOpen}
                onOpenChange={setVirtualKeyboardOpen}
              >
                <Button
                  shape="circle"
                  type={virtualKeyboardOpen ? 'primary' : 'default'}
                  icon={<KeyOutlined />}
                  disabled={!isPlaying || !remoteControlSupported}
                  aria-label="电脑键盘输入"
                  title="电脑键盘输入"
                />
              </Popover>
            </div>
          </div>

          <div className="device-stage-footer">
            {isIosStaticDebug ? (
              <>
                <Text type="secondary">模式：iOS 静态调试</Text>
                <Text type="secondary">控件：{uiElements.length}</Text>
                <Text type="secondary">投屏/触控：未开启</Text>
              </>
            ) : (
              <>
                <Text type="secondary">FPS：{fps}</Text>
                <Text type="secondary">网络延迟：{networkLatencyMs !== null ? `${networkLatencyMs}ms` : '--'}</Text>
                <Text type="secondary">首帧：{browserFirstFrameMs !== null ? `${browserFirstFrameMs}ms` : '--'}</Text>
              </>
            )}
          </div>
        </section>

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
            <>
              <div className="workspace-panel inspector-panel">
                <div className="workspace-toolbar">
                  <Space>
                    <Button type="primary" loading={loadingUiHierarchy} disabled={!selectedDevice || !inspectReady || !uiHierarchySupported} onClick={fetchUiHierarchy}>
                      获取控件
                    </Button>
                    {isIosStaticDebug && (
                      <Button icon={<ReloadOutlined />} loading={staticScreenshotLoading} disabled={!selectedDevice || !screenshotSupported} onClick={() => refreshStaticScreenshot(false)}>
                        刷新截图
                      </Button>
                    )}
                    <Button danger disabled={uiElements.length === 0} onClick={clearUiHierarchy}>
                      清理控件
                    </Button>
                  </Space>
                  <Space size={20}>
                    <Text type="secondary">当前设备：{currentDevice?.name || selectedDevice || '-'}</Text>
                    <Text type="secondary">选中：{selectedUiElement?.class_name || '-'}</Text>
                  </Space>
                </div>

                <Table
                  className="ui-property-table"
                  size="small"
                  pagination={false}
                  rowKey="key"
                  columns={[
                    {
                      title: '属性',
                      dataIndex: 'property',
                      width: 180,
                    },
                    {
                      title: '值',
                      dataIndex: 'value',
                      render: (value: string) => value ? (
                        <Text copyable={{ text: value }} className="property-value">
                          {value}
                        </Text>
                      ) : (
                        <Text type="secondary">空</Text>
                      ),
                    },
                  ]}
                  dataSource={uiPropertyRows}
                  locale={{ emptyText: uiElements.length > 0 ? '点击左侧控件框查看属性' : '暂无数据' }}
                />
              </div>

              <div className="workspace-panel log-panel">
                <div className="workspace-toolbar compact">
                  <Text strong>自动化选择器</Text>
                  <Text type="secondary">点击属性值右侧图标可复制</Text>
                </div>
                <div className="selector-preview">
                  {selectedUiElement ? (
                    <>
                      {selectedUiElement.selector_suggestions.map((selector) => (
                        <div className="selector-row" key={`${selector.type}-${selector.value}`}>
                          <Text className="selector-type">{selector.type}</Text>
                          <Text copyable={{ text: selector.value }} className="selector-value">{selector.value}</Text>
                        </div>
                      ))}
                    </>
                  ) : (
                    <Text type="secondary">选择控件后显示可用于自动化脚本的 selector。</Text>
                  )}
                </div>
              </div>
            </>
          )}

          {activeWorkspaceTab === 'script' && (
            <div className="workspace-panel script-panel">
              <div className="workspace-toolbar">
                <Space direction="vertical" size={0}>
                  <Text strong>编写自动化脚本</Text>
                  <Text type="secondary">保存后留在当前投屏页</Text>
                </Space>
                <Space>
                  <Button disabled={debugTaskActive} onClick={openScriptPicker}>
                    选择脚本
                  </Button>
                  <Button
                    danger={debugTaskActive}
                    icon={debugTaskActive ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                    loading={debugTaskActive ? debugCanceling : debugSubmitting}
                    onClick={debugTaskActive ? cancelDebugTask : runDebugScript}
                  >
                    {debugTaskActive ? '停止调试' : '运行调试'}
                  </Button>
                  <Button type="primary" onClick={openSaveScriptModal}>
                    保存
                  </Button>
                </Space>
              </div>

              <div className="script-workspace-body">
                <div className="script-ide-shell">
                  <div className="script-editor-wrap">
                    <CodeEditor
                      value={scriptContent}
                      onChange={updateScriptContent}
                      height="100%"
                      theme="vs-dark"
                      highlightedLine={activeDebugLine}
                      highlightedLineTone={failedDebugLine ? 'error' : 'current'}
                    />
                  </div>

                  <div className="script-ide-status">
                    <span>Python</span>
                    <span>app.xxx SDK</span>
                    <span>{scriptLineCount} 行</span>
                    {failedDebugLine ? <span>失败停在第 {failedDebugLine} 行</span> : null}
                    {!failedDebugLine && activeDebugLine ? <span>运行到第 {activeDebugLine} 行</span> : null}
                  </div>
                </div>

                {debugTask && (
                  <div className="script-debug-panel">
                    <div className="script-debug-header">
                      <Space size="small" wrap>
                        <Text strong>运行日志</Text>
                        <Tag color={taskStatusColors[debugTask.status]}>{taskStatusText[debugTask.status]}</Tag>
                        {failedDebugLine ? <Tag color="error">失败行 {failedDebugLine}</Tag> : null}
                        {!failedDebugLine && activeDebugLine ? <Tag color="processing">第 {activeDebugLine} 行</Tag> : null}
                        <Text type="secondary" copyable={{ text: debugTask.id }}>
                          {debugTask.id}
                        </Text>
                      </Space>
                      {debugTaskActive && (
                        <Button danger size="small" icon={<DeleteOutlined />} loading={debugCanceling} onClick={cancelDebugTask}>
                          取消任务
                        </Button>
                      )}
                    </div>

                    <div className="script-debug-summary">
                      <span>设备：{debugTask.device_id || '-'}</span>
                      <span>开始：{formatDateTime(debugTask.started_at || debugTask.created_at)}</span>
                      <span>耗时：{formatDuration(debugTask)}</span>
                    </div>

                    {debugTask.error && (
                      <Alert
                        className="script-debug-alert"
                        type="error"
                        message={debugTask.error}
                        showIcon
                      />
                    )}

                    <List
                      size="small"
                      className="script-debug-log-list"
                      dataSource={visibleDebugLogs}
                      locale={{ emptyText: '暂无日志，任务启动后会自动刷新' }}
                      renderItem={(item) => (
                        <List.Item>
                          <Space size="small" align="start">
                            <Tag color={item.level === 'ERROR' ? 'error' : item.level === 'WARN' ? 'warning' : 'default'}>
                              {item.level}
                            </Tag>
                            <Text className="script-debug-log-message">{item.message}</Text>
                          </Space>
                        </List.Item>
                      )}
                    />

                    {debugScreenshots.length > 0 && (
                      <Image.PreviewGroup>
                        <div className="script-debug-screenshots">
                          {debugScreenshots.map((src, index) => (
                            <Image key={src} width={72} src={src} alt={`debug-screenshot-${index + 1}`} />
                          ))}
                        </div>
                      </Image.PreviewGroup>
                    )}
                  </div>
                )}

                <div className="script-assist-panel">
                  <div className="script-assist-header">
                    <Text strong>当前控件代码</Text>
                    <Text type="secondary">选中控件后可插入定位片段</Text>
                  </div>
                  {selectedUiElement ? (
                    <div className="script-snippet-list script-inline-snippets">
                      {locatorSnippets.map((snippet) => (
                        <div className="script-snippet-item" key={snippet.key}>
                          <div className="script-snippet-meta">
                            <Text strong>{snippet.title}</Text>
                            <Text type="secondary">{snippet.description}</Text>
                            <pre>{snippet.code}</pre>
                          </div>
                          <Button size="small" onClick={() => appendScriptSnippet(snippet)}>
                            插入
                          </Button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <Text type="secondary">还没有选中控件。获取控件树并点击投屏上的控件后，这里会显示可插入的脚本片段。</Text>
                  )}
                </div>
              </div>
            </div>
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

      <Modal
        title="选择已保存脚本"
        open={scriptPickerOpen}
        footer={null}
        width={760}
        onCancel={() => setScriptPickerOpen(false)}
      >
        <div className="script-picker-toolbar">
          <Space direction="vertical" size={2}>
            <Text strong>脚本来源</Text>
            <Text type="secondary">载入已有脚本，或新建脚本开始编写。</Text>
          </Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={createExampleScript}>
            新建脚本
          </Button>
        </div>
        <List
          className="script-picker-list"
          loading={scriptPickerLoading}
          dataSource={savedScripts}
          locale={{ emptyText: '暂无已保存脚本' }}
          renderItem={(script) => (
            <List.Item
              actions={[
                <Button key="load" size="small" type="primary" onClick={() => selectSavedScript(script)}>
                  载入
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space size="small" wrap>
                    <Text strong>{script.name}</Text>
                    <Tag>{script.script_type}</Tag>
                    {script.status ? <Tag color={script.status === 'active' ? 'success' : 'default'}>{script.status}</Tag> : null}
                  </Space>
                }
                description={
                  <Space direction="vertical" size={2}>
                    <Text type="secondary">{script.description || '无描述'}</Text>
                    <Text type="secondary">
                      更新：{formatDateTime(script.updated_at)} · {script.content.split(/\r\n|\r|\n/).length} 行
                    </Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Modal>

      <Modal
        title="保存脚本"
        open={scriptSaveModalOpen}
        confirmLoading={scriptSaving}
        okText="保存"
        cancelText="取消"
        onOk={saveScript}
        onCancel={() => setScriptSaveModalOpen(false)}
      >
        <Form layout="vertical">
          <Form.Item label="脚本名称" required>
            <Input value={scriptName} onChange={(event) => setScriptName(event.target.value)} placeholder="请输入脚本名称" />
          </Form.Item>
          <Form.Item label="标签">
            <Select
              mode="tags"
              value={scriptTags}
              onChange={setScriptTags}
              tokenSeparators={[',']}
              placeholder="输入标签后回车"
            />
          </Form.Item>
          <Form.Item label="描述">
            <Input.TextArea
              value={scriptDescription}
              rows={3}
              onChange={(event) => setScriptDescription(event.target.value)}
              placeholder="简单描述脚本用途"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
