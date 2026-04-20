import { useEffect, useRef, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Card, Row, Col, Select, Button, Space, message, Input, Tabs, Spin } from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  FullscreenOutlined,
  VideoCameraOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import type { Device } from '@/types'
import WebrtcPlayer from '@/components/WebrtcPlayer'
import { TouchOverlay } from '@/components/TouchHandler'
import './ScreenPage.css'

const { Option } = Select

// Screen service URLs - configurable via environment variables
// Use relative URLs when served through Vite dev server proxy
const SCREEN_WS_URL = import.meta.env.VITE_SCREEN_WS_URL || ''
const SCREEN_HTTP_URL = import.meta.env.VITE_SCREEN_HTTP_URL || 'http://localhost:8002'

// Player type
type PlayerType = 'webrtc' | 'mjpeg'

export default function ScreenPage() {
  const [searchParams] = useSearchParams()
  const deviceIdFromUrl = searchParams.get('deviceId')
  const playerContainerRef = useRef<HTMLDivElement>(null)

  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDevice, setSelectedDevice] = useState<string>(deviceIdFromUrl || '')
  const [deviceInfo, setDeviceInfo] = useState<{ width: number; height: number } | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const [inputText, setInputText] = useState('')
  const [fps, setFps] = useState(0)
  const [playerType, setPlayerType] = useState<PlayerType>('mjpeg')
  const [connectionState, setConnectionState] = useState<string>('new')

  // For MJPEG fallback
  const mjpegWsRef = useRef<WebSocket | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const fpsCounterRef = useRef({ frames: 0, lastTime: Date.now() })

  // Fetch devices
  useEffect(() => {
    const fetchDevices = async () => {
      try {
        const res = await fetch('/api/v1/devices')
        const data = await res.json()
        setDevices(data.devices || [])
      } catch (e) {
        console.error('Failed to fetch devices:', e)
      }
    }
    fetchDevices()
    const interval = setInterval(fetchDevices, 5000)
    return () => clearInterval(interval)
  }, [])

  // Fetch device screen info when device changes
  useEffect(() => {
    const fetchDeviceInfo = async () => {
      if (!selectedDevice) {
        setDeviceInfo(null)
        return
      }
      try {
        const res = await fetch(`/api/v1/devices/${selectedDevice}`)
        const data = await res.json()
        // Parse screen resolution (e.g., "1080x2400")
        const resolution = data.data?.screenResolution || '1080x1920'
        const [width, height] = resolution.split('x').map(Number)
        setDeviceInfo({ width: width || 1080, height: height || 1920 })
      } catch (e) {
        console.error('Failed to fetch device info:', e)
        setDeviceInfo({ width: 1080, height: 1920 }) // Default
      }
    }
    fetchDeviceInfo()
  }, [selectedDevice])

  // Send input to device
  const sendInput = useCallback(
    async (type: string, x: number, y: number, extra?: Record<string, unknown>) => {
      if (!selectedDevice || !isPlaying) return

      try {
        const body: Record<string, unknown> = { action: type, x, y, ...extra }
        await fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${selectedDevice}/touch`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
      } catch (e) {
        console.error('Failed to send input:', e)
      }
    },
    [selectedDevice, isPlaying]
  )

  // Handle touch input
  const handleTouchInput = useCallback(
    (type: string, x: number, y: number, extra?: Record<string, unknown>) => {
      console.log('Touch input:', type, x, y, extra)
      sendInput(type, x, y, extra)
    },
    [sendInput]
  )

  // MJPEG WebSocket connection (fallback)
  const connectMjpegWebSocket = useCallback(() => {
    if (!selectedDevice) return

    // Use relative URL for Vite dev server proxy, or construct WebSocket URL from window.location
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = window.location.host
    const wsUrl = SCREEN_WS_URL
      ? `${SCREEN_WS_URL}/ws/${selectedDevice}/stream`
      : `${wsProtocol}//${wsHost}/ws/${selectedDevice}/stream`

    console.log('Connecting to MJPEG WebSocket:', wsUrl)

    const ws = new WebSocket(wsUrl)
    mjpegWsRef.current = ws

    ws.onopen = () => {
      console.log('MJPEG WebSocket connected')
      setLoading(false)
      message.success('投屏连接成功')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'frame' && data.data) {
          const img = new Image()
          img.onload = () => {
            const canvas = canvasRef.current
            if (canvas) {
              const ctx = canvas.getContext('2d')
              if (ctx) {
                const containerWidth = canvas.parentElement?.clientWidth || 480
                const containerHeight = canvas.parentElement?.clientHeight || 800
                const scale = Math.min(containerWidth / img.width, containerHeight / img.height)

                canvas.width = img.width * scale
                canvas.height = img.height * scale

                ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
              }
            }

            // FPS counter
            fpsCounterRef.current.frames++
            const now = Date.now()
            if (now - fpsCounterRef.current.lastTime >= 1000) {
              setFps(fpsCounterRef.current.frames)
              fpsCounterRef.current.frames = 0
              fpsCounterRef.current.lastTime = now
            }
          }
          img.src = `data:image/jpeg;base64,${data.data}`
        }
      } catch (e) {
        // Ignore parse errors
      }
    }

    ws.onerror = () => {
      message.error('投屏连接失败')
      setIsPlaying(false)
    }

    ws.onclose = () => {
      console.log('MJPEG WebSocket closed')
    }
  }, [selectedDevice])

  // Handle WebRTC stats
  const handleWebRTCStats = useCallback((stats: { fps: number; bytesReceived: number }) => {
    setFps(stats.fps)
  }, [])

  // Handle WebRTC connection state
  const handleConnectionStateChange = useCallback((state: string) => {
    setConnectionState(state)
    if (state === 'connected') {
      setLoading(false)
      message.success('投屏连接成功')
    } else if (state === 'failed') {
      message.error('投屏连接失败')
      setIsPlaying(false)
    }
  }, [])

  // Start/stop streaming
  useEffect(() => {
    if (isPlaying && selectedDevice) {
      setLoading(true)
      if (playerType === 'mjpeg') {
        connectMjpegWebSocket()
      }
    } else if (mjpegWsRef.current) {
      mjpegWsRef.current.close()
      mjpegWsRef.current = null
    }

    return () => {
      if (mjpegWsRef.current) {
        mjpegWsRef.current.close()
      }
    }
  }, [isPlaying, selectedDevice, playerType, connectMjpegWebSocket])

  // Send key event
  const sendKey = async (keycode: string) => {
    if (!selectedDevice) return
    try {
      if (keycode === 'KEYCODE_HOME') {
        await fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${selectedDevice}/home`, { method: 'POST' })
        return
      }
      if (keycode === 'KEYCODE_BACK') {
        await fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${selectedDevice}/back`, { method: 'POST' })
        return
      }

      const keyMap: Record<string, number> = {
        'KEYCODE_APP_SWITCH': 187,
        'KEYCODE_POWER': 26,
        'KEYCODE_VOLUME_UP': 24,
        'KEYCODE_VOLUME_DOWN': 25,
      }

      await fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${selectedDevice}/key`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyCode: keyMap[keycode] || 0, action: 'down_up' }),
      })
    } catch (e) {
      console.error('Failed to send key:', e)
    }
  }

  // Send text
  const sendTextToDevice = async () => {
    if (!inputText.trim() || !selectedDevice) return
    try {
      await fetch(`${SCREEN_HTTP_URL}/api/v1/sessions/${selectedDevice}/text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: inputText }),
      })
      setInputText('')
      message.success('文本已发送')
    } catch (e) {
      message.error('发送失败')
    }
  }

  // Fullscreen
  const handleFullscreen = () => {
    if (playerContainerRef.current) {
      playerContainerRef.current.requestFullscreen()
    }
  }

  // Reconnect
  const handleReconnect = () => {
    setIsPlaying(false)
    setTimeout(() => setIsPlaying(true), 500)
  }

  const availableDevices = devices.filter((d) => d.status === 'online' || d.status === 'busy')

  return (
    <div className="screen-page">
      <Row gutter={24}>
        <Col span={18}>
          <Card
            title={
              <Space>
                <VideoCameraOutlined />
                <span>投屏控制台</span>
                {selectedDevice && (
                  <span style={{ color: '#999', fontSize: 14 }}>
                    ({devices.find((d) => d.id === selectedDevice)?.name || selectedDevice})
                  </span>
                )}
                {fps > 0 && <span style={{ color: '#52c41a', fontSize: 12 }}>{fps} FPS</span>}
              </Space>
            }
            extra={
              <Space>
                <Select
                  value={playerType}
                  style={{ width: 120 }}
                  onChange={setPlayerType}
                  disabled={isPlaying}
                >
                  <Option value="webrtc">WebRTC</Option>
                  <Option value="mjpeg">MJPEG</Option>
                </Select>
                <Select
                  value={selectedDevice}
                  style={{ width: 200 }}
                  placeholder="选择设备"
                  onChange={(val) => {
                    setSelectedDevice(val)
                    setIsPlaying(false)
                  }}
                >
                  {availableDevices.map((device) => (
                    <Option key={device.id} value={device.id}>
                      {device.name}
                    </Option>
                  ))}
                </Select>
                <Button
                  type={isPlaying ? 'default' : 'primary'}
                  icon={isPlaying ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                  onClick={() => setIsPlaying(!isPlaying)}
                  disabled={!selectedDevice}
                  loading={loading}
                >
                  {isPlaying ? '断开' : '连接'}
                </Button>
              </Space>
            }
          >
            <div
              ref={playerContainerRef}
              className={`player-container ${isPlaying ? 'active' : ''}`}
              style={{
                position: 'relative',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: '#000',
                minHeight: 500,
                borderRadius: 8,
                overflow: 'hidden',
              }}
            >
              {loading && (
                <div style={{ position: 'absolute', zIndex: 10 }}>
                  <Spin size="large" />
                </div>
              )}

              {isPlaying ? (
                playerType === 'webrtc' ? (
                  <TouchOverlay
                    screenWidth={deviceInfo?.width || 1080}
                    screenHeight={deviceInfo?.height || 1920}
                    onInput={handleTouchInput}
                    showIndicator={true}
                  >
                    <WebrtcPlayer
                      deviceId={selectedDevice}
                      wsUrl={`${SCREEN_WS_URL}/ws/signaling`}
                      onConnectionStateChange={handleConnectionStateChange}
                      onStats={handleWebRTCStats}
                    />
                  </TouchOverlay>
                ) : (
                  <TouchOverlay
                    screenWidth={deviceInfo?.width || 1080}
                    screenHeight={deviceInfo?.height || 1920}
                    onInput={handleTouchInput}
                    showIndicator={true}
                  >
                    <canvas
                      ref={canvasRef}
                      style={{ cursor: 'pointer', maxWidth: '100%', maxHeight: '100%' }}
                    />
                  </TouchOverlay>
                )
              ) : (
                <div style={{ textAlign: 'center', color: '#666' }}>
                  <VideoCameraOutlined style={{ fontSize: 64, marginBottom: 16 }} />
                  <p>选择设备并点击连接开始投屏</p>
                  {availableDevices.length === 0 && (
                    <p style={{ color: '#ff4d4f' }}>没有可用设备</p>
                  )}
                </div>
              )}
            </div>
          </Card>
        </Col>

        <Col span={6}>
          <Card title="控制面板">
            <Tabs
              items={[
                {
                  key: 'control',
                  label: '按键控制',
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          marginBottom: 8,
                        }}
                      >
                        <span>连接状态</span>
                        <span style={{ color: isPlaying ? '#52c41a' : '#999' }}>
                          {connectionState}
                        </span>
                      </div>
                      <Button block onClick={() => sendKey('KEYCODE_HOME')}>
                        Home
                      </Button>
                      <Button block onClick={() => sendKey('KEYCODE_BACK')}>
                        返回
                      </Button>
                      <Button block onClick={() => sendKey('KEYCODE_APP_SWITCH')}>
                        多任务
                      </Button>
                      <Button block onClick={() => sendKey('KEYCODE_POWER')}>
                        电源键
                      </Button>
                      <Button block onClick={() => sendKey('KEYCODE_VOLUME_UP')}>
                        音量+
                      </Button>
                      <Button block onClick={() => sendKey('KEYCODE_VOLUME_DOWN')}>
                        音量-
                      </Button>
                      <Button block onClick={handleFullscreen} icon={<FullscreenOutlined />}>
                        全屏
                      </Button>
                      <Button block onClick={handleReconnect} icon={<ReloadOutlined />}>
                        重连
                      </Button>
                    </Space>
                  ),
                },
                {
                  key: 'gesture',
                  label: '手势操作',
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Button
                        block
                        onClick={() => {
                          const w = deviceInfo?.width || 1080
                          const h = deviceInfo?.height || 1920
                          sendInput('swipe', w / 2, h * 0.8, { endX: w / 2, endY: h * 0.2 })
                        }}
                      >
                        下拉通知栏
                      </Button>
                      <Button
                        block
                        onClick={() => {
                          const w = deviceInfo?.width || 1080
                          const h = deviceInfo?.height || 1920
                          sendInput('swipe', w / 2, h * 0.2, { endX: w / 2, endY: h * 0.8 })
                        }}
                      >
                        上拉
                      </Button>
                      <Button
                        block
                        onClick={() => {
                          const w = deviceInfo?.width || 1080
                          const h = deviceInfo?.height || 1920
                          sendInput('swipe', w * 0.1, h / 2, { endX: w * 0.9, endY: h / 2 })
                        }}
                      >
                        左滑
                      </Button>
                      <Button
                        block
                        onClick={() => {
                          const w = deviceInfo?.width || 1080
                          const h = deviceInfo?.height || 1920
                          sendInput('swipe', w * 0.9, h / 2, { endX: w * 0.1, endY: h / 2 })
                        }}
                      >
                        右滑
                      </Button>
                    </Space>
                  ),
                },
                {
                  key: 'quick',
                  label: '快捷输入',
                  children: (
                    <>
                      <Input.TextArea
                        placeholder="输入文本后点击发送"
                        rows={4}
                        value={inputText}
                        onChange={(e) => setInputText(e.target.value)}
                      />
                      <Button
                        type="primary"
                        block
                        style={{ marginTop: 8 }}
                        onClick={sendTextToDevice}
                      >
                        发送到设备
                      </Button>
                    </>
                  ),
                },
              ]}
            />
          </Card>

          {/* Device info card */}
          {deviceInfo && (
            <Card title="设备信息" style={{ marginTop: 16 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>分辨率</span>
                  <span>{deviceInfo.width}x{deviceInfo.height}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>播放器</span>
                  <span>{playerType.toUpperCase()}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>帧率</span>
                  <span>{fps} FPS</span>
                </div>
              </Space>
            </Card>
          )}
        </Col>
      </Row>
    </div>
  )
}
