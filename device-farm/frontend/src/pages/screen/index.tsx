import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Space, message, Typography, Table } from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  FullscreenOutlined,
  VideoCameraOutlined,
  HomeOutlined,
  RollbackOutlined,
  AppstoreOutlined,
} from '@ant-design/icons'
import { Room } from 'livekit-client'
import type { Device } from '@/types'
import WebrtcPlayer from '@/components/WebrtcPlayer'
import { TouchOverlay } from '@/components/TouchHandler'
import { formatDeviceOs, mapDevice } from '@/utils/device'
import './ScreenPage.css'

const { Text } = Typography

const SCREEN_HTTP_URL = import.meta.env.VITE_SCREEN_HTTP_URL || ''
const TOUCH_MOVE_INTERVAL_MS = 16

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

export default function ScreenPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const deviceIdFromUrl = searchParams.get('deviceId')
  const missingDeviceMessageShownRef = useRef(false)
  const playerContainerRef = useRef<HTMLDivElement>(null)

  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDevice, setSelectedDevice] = useState<string>(deviceIdFromUrl || '')
  const [deviceInfo, setDeviceInfo] = useState<{ width: number; height: number } | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(Boolean(deviceIdFromUrl))
  const [fps, setFps] = useState(0)
  const [connectionState, setConnectionState] = useState<string>('idle')
  const [hasVideoFrame, setHasVideoFrame] = useState(false)
  const [uiElements, setUiElements] = useState<UIElementNode[]>([])
  const [selectedUiElement, setSelectedUiElement] = useState<UIElementNode | null>(null)
  const [loadingUiHierarchy, setLoadingUiHierarchy] = useState(false)
  const [renderMetrics, setRenderMetrics] = useState<RenderMetrics | null>(null)
  const [uiScreen, setUiScreen] = useState<{ width: number; height: number } | null>(null)
  const currentDevice = devices.find((d) => d.id === selectedDevice)
  const screenMirrorSupported = currentDevice?.capabilities.screenMirror ?? Boolean(selectedDevice)
  const remoteControlSupported = currentDevice?.capabilities.remoteControl ?? Boolean(selectedDevice)
  const uiHierarchySupported = currentDevice?.capabilities.uiHierarchy ?? Boolean(selectedDevice)
  
  // LiveKit state
  const [lkSession, setLkSession] = useState<{ url: string; token: string } | null>(null)
  const lkRoomRef = useRef<Room | null>(null)
  const pendingMoveRef = useRef<{ x: number; y: number } | null>(null)
  const moveTimerRef = useRef<number | null>(null)
  const autoStartedDeviceRef = useRef<string | null>(null)

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
      } catch (e) {
        setDeviceInfo({ width: 1080, height: 1920 })
      }
    }
    fetchDeviceInfo()
  }, [selectedDevice])

  // Start session on backend
  const startSession = useCallback(async () => {
    if (!selectedDevice) return
    if (currentDevice && !currentDevice.capabilities.screenMirror) {
      message.error('当前设备连接不支持投屏')
      return
    }
    setLoading(true)
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
        setConnectionState('connecting')
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
  }, [currentDevice, selectedDevice])

  useEffect(() => {
    if (!selectedDevice || isPlaying || lkSession || autoStartedDeviceRef.current === selectedDevice) return

    autoStartedDeviceRef.current = selectedDevice
    void startSession()
  }, [isPlaying, lkSession, selectedDevice, startSession])

  const stopSession = async () => {
    if (!selectedDevice) return
    setIsPlaying(false)
    setLkSession(null)
    setHasVideoFrame(false)
    setConnectionState('idle')
    clearUiHierarchy()
    flushPendingMove()
    lkRoomRef.current = null
    try {
      await fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${selectedDevice}/stop`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch (e) {
      console.error('Failed to stop session:', e)
    }
  }

  const publishControl = useCallback((payload: Record<string, unknown>, reliable = false) => {
    const room = lkRoomRef.current
    if (!room || room.state !== 'connected') return

    const encoder = new TextEncoder()
    void room.localParticipant.publishData(encoder.encode(JSON.stringify(payload)), {
      reliable,
      topic: 'control',
    })
  }, [])

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

  const handleWebRTCStats = useCallback((stats: { fps: number; bytesReceived: number }) => {
    setFps(stats.fps)
  }, [])

  const clearUiHierarchy = useCallback(() => {
    setUiElements([])
    setSelectedUiElement(null)
    setUiScreen(null)
  }, [])

  const fetchUiHierarchy = useCallback(async () => {
    if (!selectedDevice) return
    if (!isPlaying) {
      message.warning('请先连接投屏后再获取控件')
      return
    }
    if (currentDevice && !currentDevice.capabilities.uiHierarchy) {
      message.warning('当前设备连接不支持获取控件')
      return
    }

    setLoadingUiHierarchy(true)
    try {
      const res = await fetch(`/api/v1/devices/${selectedDevice}/ui-hierarchy`, {
        credentials: 'include',
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
      }
      message.success(`获取到 ${result.elements?.length || 0} 个控件，点击控件框查看属性`)
    } catch (e) {
      const error = e as Error
      message.error(error.message || '获取控件失败')
    } finally {
      setLoadingUiHierarchy(false)
    }
  }, [currentDevice, isPlaying, selectedDevice])

  const handleConnectionStateChange = useCallback((state: string) => {
    setConnectionState(state)
    if (state === 'disconnected') {
      setHasVideoFrame(false)
    }
    if (state === 'connected') {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    return () => {
      if (moveTimerRef.current) {
        window.clearTimeout(moveTimerRef.current)
      }
    }
  }, [])

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

  // Send key event via DataChannel
  const sendKey = (keycode: string) => {
    const room = lkRoomRef.current
    if (!room || room.state !== 'connected' || !remoteControlSupported) return

    const keyMap: Record<string, number> = {
      'KEYCODE_HOME': 3,
      'KEYCODE_BACK': 4,
      'KEYCODE_APP_SWITCH': 187,
      'KEYCODE_POWER': 26,
    }

    const keyCode = keyMap[keycode]
    if (!keyCode) return

    publishControl({ type: 'key', action: 'down', keyCode }, true)
    window.setTimeout(() => {
      publishControl({ type: 'key', action: 'up', keyCode }, true)
    }, 50)
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
        <section className="device-stage">
          <div className="device-stage-header">
            <div className="device-context">
              <VideoCameraOutlined />
              <span>{currentDevice?.name || selectedDevice || '未选择设备'}</span>
              {currentDevice && <Text type="secondary">{formatDeviceOs(currentDevice)}</Text>}
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
            <div
              ref={playerContainerRef}
              className={`player-container ${isPlaying ? 'active' : ''}`}
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
                    onConnectionStateChange={handleConnectionStateChange}
                    onStats={handleWebRTCStats}
                    onFirstFrame={() => {
                      setHasVideoFrame(true)
                      setLoading(false)
                    }}
                    onRoomCreated={(room) => { lkRoomRef.current = room; }}
                  />
                  {!hasVideoFrame && (
                    <div className="video-waiting-overlay">
                      等待视频画面...
                    </div>
                  )}
                  {uiElements.length > 0 && renderMetrics && uiScreen && (
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
                  )}
                </TouchOverlay>
              ) : (
                <div className="player-placeholder">
                  <VideoCameraOutlined style={{ fontSize: 56, marginBottom: 16 }} />
                  <p>从设备管理选择设备后点击连接开始投屏</p>
                </div>
              )}
            </div>

            <div className="device-rail">
              <Button shape="circle" icon={<HomeOutlined />} disabled={!remoteControlSupported} onClick={() => sendKey('KEYCODE_HOME')} />
              <Button shape="circle" icon={<RollbackOutlined />} disabled={!remoteControlSupported} onClick={() => sendKey('KEYCODE_BACK')} />
              <Button shape="circle" icon={<AppstoreOutlined />} disabled={!remoteControlSupported} onClick={() => sendKey('KEYCODE_APP_SWITCH')} />
              <Button shape="circle" icon={<FullscreenOutlined />} onClick={handleFullscreen} />
            </div>
          </div>

          <div className="device-stage-footer">
            <Text type="secondary">状态：{connectionState}</Text>
            <Text type="secondary">FPS：{fps}</Text>
            {uiElements.length > 0 && <Text type="secondary">控件：{uiElements.length}</Text>}
          </div>
        </section>

        <section className="screen-workspace">
          <div className="workspace-tabs">
            <button type="button" className="workspace-tab active">控件检查</button>
            <button type="button" className="workspace-tab">脚本辅助</button>
            <button type="button" className="workspace-tab">Logcat</button>
          </div>

          <div className="workspace-panel inspector-panel">
            <div className="workspace-toolbar">
              <Space>
                <Button type="primary" loading={loadingUiHierarchy} disabled={!selectedDevice || !isPlaying || !uiHierarchySupported} onClick={fetchUiHierarchy}>
                  获取控件
                </Button>
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
              scroll={{ y: 330 }}
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
                selectedUiElement.selector_suggestions.map((selector) => (
                  <div className="selector-row" key={`${selector.type}-${selector.value}`}>
                    <Text className="selector-type">{selector.type}</Text>
                    <Text copyable={{ text: selector.value }} className="selector-value">{selector.value}</Text>
                  </div>
                ))
              ) : (
                <Text type="secondary">选择控件后显示可用于自动化脚本的 id、accessibility_id、text 和 xpath。</Text>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
