import { useEffect, useRef, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Card, Row, Col, Select, Button, Space, message, Typography } from 'antd'
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  FullscreenOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { Room } from 'livekit-client'
import type { Device } from '@/types'
import WebrtcPlayer from '@/components/WebrtcPlayer'
import { TouchOverlay } from '@/components/TouchHandler'
import './ScreenPage.css'

const { Option } = Select
const { Text } = Typography

const SCREEN_HTTP_URL = import.meta.env.VITE_SCREEN_HTTP_URL || ''
const TOUCH_MOVE_INTERVAL_MS = 16

export default function ScreenPage() {
  const [searchParams] = useSearchParams()
  const deviceIdFromUrl = searchParams.get('deviceId')
  const playerContainerRef = useRef<HTMLDivElement>(null)

  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDevice, setSelectedDevice] = useState<string>(deviceIdFromUrl || '')
  const [deviceInfo, setDeviceInfo] = useState<{ width: number; height: number } | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const [fps, setFps] = useState(0)
  const [connectionState, setConnectionState] = useState<string>('idle')
  const [hasVideoFrame, setHasVideoFrame] = useState(false)
  
  // LiveKit state
  const [lkSession, setLkSession] = useState<{ url: string; token: string } | null>(null)
  const lkRoomRef = useRef<Room | null>(null)
  const pendingMoveRef = useRef<{ x: number; y: number } | null>(null)
  const moveTimerRef = useRef<number | null>(null)

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
  const startSession = async () => {
    if (!selectedDevice) return
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
  }

  const stopSession = async () => {
    if (!selectedDevice) return
    setIsPlaying(false)
    setLkSession(null)
    setHasVideoFrame(false)
    setConnectionState('idle')
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
      if (type !== 'touch') return
      const action = extra?.action || 'move'
      if (action === 'move') {
        scheduleMove(x, y)
        return
      }

      flushPendingMove()
      publishControl({ type: 'touch', action, x, y }, true)
    },
    [flushPendingMove, publishControl, scheduleMove]
  )

  const handleWebRTCStats = useCallback((stats: { fps: number; bytesReceived: number }) => {
    setFps(stats.fps)
  }, [])

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

  // Send key event via DataChannel
  const sendKey = (keycode: string) => {
    const room = lkRoomRef.current
    if (!room || room.state !== 'connected') return

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

  const availableDevices = devices.filter((d) => d.status === 'online' || d.status === 'busy')

  return (
    <div className="screen-page">
      <Row gutter={24}>
        <Col span={18}>
          <Card
            title={
              <Space>
                <VideoCameraOutlined />
                <span>极速投屏控制台 (WebRTC + SFU)</span>
                {selectedDevice && (
                  <span style={{ color: '#999', fontSize: 14 }}>
                    ({devices.find((d) => d.id === selectedDevice)?.name || selectedDevice})
                  </span>
                )}
              </Space>
            }
            extra={
              <Space>
                <Select
                  value={selectedDevice}
                  style={{ width: 200 }}
                  placeholder="选择设备"
                  onChange={(val) => {
                    setSelectedDevice(val)
                    if (isPlaying) stopSession()
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
                  onClick={() => isPlaying ? stopSession() : startSession()}
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
                minHeight: 600,
                borderRadius: 8,
                overflow: 'hidden',
              }}
            >
              {isPlaying && lkSession ? (
                <TouchOverlay
                  screenWidth={deviceInfo?.width || 1080}
                  screenHeight={deviceInfo?.height || 1920}
                  onInput={handleTouchInput}
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
                    <div
                      style={{
                        position: 'absolute',
                        inset: 0,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#bfbfbf',
                        background: '#000',
                        pointerEvents: 'none',
                      }}
                    >
                      等待视频画面...
                    </div>
                  )}
                </TouchOverlay>
              ) : (
                <div style={{ textAlign: 'center', color: '#666' }}>
                  <VideoCameraOutlined style={{ fontSize: 64, marginBottom: 16 }} />
                  <p>选择设备并点击连接开始极速投屏</p>
                </div>
              )}
            </div>
          </Card>
        </Col>

        <Col span={6}>
          <Card title="极速控制">
             <Space direction="vertical" style={{ width: '100%' }}>
                <Button block onClick={() => sendKey('KEYCODE_HOME')}>Home</Button>
                <Button block onClick={() => sendKey('KEYCODE_BACK')}>返回</Button>
                <Button block onClick={() => sendKey('KEYCODE_APP_SWITCH')}>多任务</Button>
                <Button block onClick={handleFullscreen} icon={<FullscreenOutlined />}>全屏</Button>
                
	                <div style={{ marginTop: 20 }}>
	                    <Text type="secondary">连接状态: {connectionState}</Text>
	                    <br />
	                    <Text type="secondary">FPS: {fps}</Text>
	                </div>
             </Space>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
