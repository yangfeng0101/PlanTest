import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { message } from 'antd'
import type { Room } from 'livekit-client'
import type { Device } from '@/types'
import type { ScreenSessionDiagnostics } from './types'
import {
  TOUCH_MOVE_INTERVAL_MS,
  buildIOSMJPEGStreamUrl,
  fetchSessionDiagnostics,
  prepareIOSMJPEGSession,
  requestStopIOSMJPEG,
  requestStopSession,
  startLiveKitSession,
} from './api'

interface UseScreenSessionOptions {
  selectedDevice: string
  devicesLoaded: boolean
  currentDevice: Device | undefined
  isIosDevice: boolean
  isIosLivePreview: boolean
  isIosStaticDebug: boolean
  isIosDirectMjpegMirror: boolean
  remoteControlSupported: boolean
  onIosLogicalScreen: (screen?: { width?: number; height?: number } | null) => void
  onVideoScreen: (screen: { width: number; height: number }) => void
  onStopCleanup: () => void
}

export default function useScreenSession({
  selectedDevice,
  devicesLoaded,
  currentDevice,
  isIosDevice,
  isIosLivePreview,
  isIosStaticDebug,
  isIosDirectMjpegMirror,
  remoteControlSupported,
  onIosLogicalScreen,
  onVideoScreen,
  onStopCleanup,
}: UseScreenSessionOptions) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [loading, setLoading] = useState(Boolean(selectedDevice))
  const [fps, setFps] = useState(0)
  const [hasVideoFrame, setHasVideoFrame] = useState(false)
  const [sessionDiagnostics, setSessionDiagnostics] = useState<ScreenSessionDiagnostics | null>(null)
  const [browserFirstFrameMs, setBrowserFirstFrameMs] = useState<number | null>(null)
  const [networkLatencyMs, setNetworkLatencyMs] = useState<number | null>(null)
  const [lkSession, setLkSession] = useState<{ url: string; token: string } | null>(null)
  const [mjpegStreamKey, setMjpegStreamKey] = useState(0)

  const lkRoomRef = useRef<Room | null>(null)
  const pendingMoveRef = useRef<{ x: number; y: number } | null>(null)
  const moveTimerRef = useRef<number | null>(null)
  const autoStartedDeviceRef = useRef<string | null>(null)
  const autoStartBlockedRef = useRef<string | null>(null)
  const startRequestedAtRef = useRef<number | null>(null)
  const activeSessionDeviceRef = useRef<string | null>(null)
  const activeSessionKindRef = useRef<'livekit' | 'ios-mjpeg' | null>(null)

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
        onIosLogicalScreen(prepareData.screen)
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
        onVideoScreen({ width: videoWidth, height: videoHeight })
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
  }, [currentDevice, devicesLoaded, isIosDevice, isIosDirectMjpegMirror, isIosLivePreview, onIosLogicalScreen, onVideoScreen, selectedDevice])

  const stopSession = useCallback(async () => {
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
    onStopCleanup()
    flushPendingMove()
    lkRoomRef.current = null
    if (sessionKind === 'ios-mjpeg') {
      requestStopIOSMJPEG(selectedDevice)
    }
    requestStopSession(selectedDevice)
  }, [flushPendingMove, onStopCleanup, selectedDevice])

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

  const handleConnectionStateChange = useCallback((state: string) => {
    if (state === 'disconnected') {
      setHasVideoFrame(false)
    }
    if (state === 'connected') {
      setLoading(false)
    }
  }, [])

  const handleWebRTCStats = useCallback((stats: { fps: number; bytesReceived: number; latencyMs?: number }) => {
    setFps(stats.fps)
    if (typeof stats.latencyMs === 'number') {
      setNetworkLatencyMs(stats.latencyMs)
    }
  }, [])

  const markVideoFirstFrame = useCallback(() => {
    setHasVideoFrame(true)
    setLoading(false)
    if (startRequestedAtRef.current !== null) {
      setBrowserFirstFrameMs(Math.round(performance.now() - startRequestedAtRef.current))
    }
  }, [])

  const handleIOSMJPEGLoad = useCallback(() => {
    markVideoFirstFrame()
    setSessionDiagnostics((current) => current && { ...current, last_error: undefined })
  }, [markVideoFirstFrame])

  const handleIOSMJPEGError = useCallback(() => {
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
  }, [selectedDevice])

  const handleRoomCreated = useCallback((room: Room) => {
    lkRoomRef.current = room
  }, [])

  const iosMjpegStreamUrl = useMemo(() => {
    if (!selectedDevice || !isPlaying || !isIosDirectMjpegMirror || !mjpegStreamKey) return ''
    return buildIOSMJPEGStreamUrl(selectedDevice, mjpegStreamKey)
  }, [isIosDirectMjpegMirror, isPlaying, mjpegStreamKey, selectedDevice])

  const hasStartupError = !isIosStaticDebug && Boolean(sessionDiagnostics?.last_error)
  const isInitializing = !isIosStaticDebug && !hasVideoFrame && !hasStartupError
  const statusDotClassName = isIosStaticDebug
    ? 'connected'
    : hasVideoFrame
    ? 'connected'
    : hasStartupError
      ? 'error'
      : 'connecting'

  return {
    isPlaying,
    loading,
    fps,
    hasVideoFrame,
    sessionDiagnostics,
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
    handleWebRTCFirstFrame: markVideoFirstFrame,
    handleRoomCreated,
  }
}
