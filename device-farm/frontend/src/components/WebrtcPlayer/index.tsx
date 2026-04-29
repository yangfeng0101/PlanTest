import { useCallback, useEffect, useRef } from 'react'
import {
  LiveKitRoom,
  VideoTrack,
  useTracks,
  RoomAudioRenderer,
  useRoomContext,
} from '@livekit/components-react'
import { Track, Room } from 'livekit-client'
import '@livekit/components-styles'

interface WebrtcPlayerProps {
  deviceId: string
  token: string
  serverUrl: string
  onConnectionStateChange?: (state: string) => void
  onStats?: (stats: { fps: number; bytesReceived: number; latencyMs?: number }) => void
  onRoomCreated?: (room: Room) => void
  onFirstFrame?: () => void
  waitingText?: string
}

export default function WebrtcPlayer({
  token,
  serverUrl,
  onConnectionStateChange,
  onRoomCreated,
  onFirstFrame,
  waitingText,
  onStats,
}: WebrtcPlayerProps) {
  if (!token || !serverUrl) {
    return (
      <div style={{ color: '#fff', textAlign: 'center', padding: '20px' }}>
        等待连接参数 (Token/URL)...
      </div>
    )
  }

  return (
    <div className="webrtc-player" style={{ width: '100%', height: '100%', position: 'relative' }}>
      <LiveKitRoom
        video={false}
        audio={false}
        token={token}
        serverUrl={serverUrl}
        onDisconnected={() => onConnectionStateChange?.('disconnected')}
        onConnected={() => onConnectionStateChange?.('connected')}
        style={{ height: '100%' }}
      >
        <RoomBinder onRoomCreated={onRoomCreated} />
        <VideoContainer onFirstFrame={onFirstFrame} onStats={onStats} waitingText={waitingText} />
        <RoomAudioRenderer />
      </LiveKitRoom>
    </div>
  )
}

function RoomBinder({ onRoomCreated }: { onRoomCreated?: (room: Room) => void }) {
  const room = useRoomContext()

  useEffect(() => {
    onRoomCreated?.(room)
  }, [room, onRoomCreated])

  return null
}

function VideoContainer({
  onFirstFrame,
  onStats,
  waitingText,
}: {
  onFirstFrame?: () => void
  onStats?: (stats: { fps: number; bytesReceived: number; latencyMs?: number }) => void
  waitingText?: string
}) {
  const tracks = useTracks([Track.Source.ScreenShare, Track.Source.Camera])
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const hasFirstFrameRef = useRef(false)
  const statsRef = useRef({ lastFrames: 0, lastTime: 0 })

  // We expect the agent to publish a track
  const track = tracks[0]

  useEffect(() => {
    hasFirstFrameRef.current = false
    statsRef.current = { lastFrames: 0, lastTime: performance.now() }
  }, [track?.publication?.trackSid])

  const markFirstFrame = useCallback(() => {
    const video = videoRef.current
    if (!video || hasFirstFrameRef.current || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return

    hasFirstFrameRef.current = true
    onFirstFrame?.()
  }, [onFirstFrame])

  useEffect(() => {
    if (!track || !onStats) return

    const timer = window.setInterval(() => {
      void collectVideoStats(track as unknown as StatsCapableTrack, videoRef.current, statsRef.current).then((stats) => {
        if (!stats) return
        statsRef.current = stats.nextFrameState
        onStats({
          fps: stats.fps,
          bytesReceived: stats.bytesReceived,
          latencyMs: stats.latencyMs,
        })
      })
    }, 1000)

    return () => window.clearInterval(timer)
  }, [track, onStats])

  if (!track) {
    return (
      <div style={{ 
        position: 'absolute', 
        top: 0, left: 0, right: 0, bottom: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: '#666' 
      }}>
        {waitingText ?? '等待视频流...'}
      </div>
    )
  }

  return (
    <VideoTrack
      ref={videoRef}
      trackRef={track}
      onLoadedData={markFirstFrame}
      onCanPlay={markFirstFrame}
      onPlaying={markFirstFrame}
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'contain',
        backgroundColor: '#000',
      }}
    />
  )
}

type FrameStatsState = {
  lastFrames: number
  lastTime: number
}

type StatsCapableTrack = {
  publication?: {
    track?: {
      getRTCStatsReport?: () => Promise<RTCStatsReport | undefined>
    }
  }
}

async function collectVideoStats(
  track: StatsCapableTrack,
  video: HTMLVideoElement | null,
  frameState: FrameStatsState,
) {
  if (!video || typeof video.getVideoPlaybackQuality !== 'function') return null

  const quality = video.getVideoPlaybackQuality()
  const now = performance.now()
  const elapsedSeconds = (now - frameState.lastTime) / 1000
  const frameDelta = quality.totalVideoFrames - frameState.lastFrames
  const fps = elapsedSeconds > 0 ? Math.max(0, Math.round(frameDelta / elapsedSeconds)) : 0
  const report = await track.publication?.track?.getRTCStatsReport?.()

  return {
    fps,
    bytesReceived: readBytesReceived(report),
    latencyMs: readLatencyMs(report),
    nextFrameState: {
      lastFrames: quality.totalVideoFrames,
      lastTime: now,
    },
  }
}

function readLatencyMs(report?: RTCStatsReport) {
  if (!report) return undefined

  let fallbackSeconds: number | undefined
  let selectedSeconds: number | undefined
  report.forEach((stat) => {
    const value = typeof stat.currentRoundTripTime === 'number'
      ? stat.currentRoundTripTime
      : typeof stat.roundTripTime === 'number'
        ? stat.roundTripTime
        : undefined
    if (typeof value !== 'number') return

    fallbackSeconds = value
    if (stat.type === 'candidate-pair' && stat.state === 'succeeded' && stat.nominated) {
      selectedSeconds = value
    }
  })

  const seconds = selectedSeconds ?? fallbackSeconds
  return typeof seconds === 'number' ? Math.round(seconds * 1000) : undefined
}

function readBytesReceived(report?: RTCStatsReport) {
  if (!report) return 0

  let bytesReceived = 0
  report.forEach((stat) => {
    if (stat.type === 'inbound-rtp' && stat.kind === 'video' && typeof stat.bytesReceived === 'number') {
      bytesReceived = Math.max(bytesReceived, stat.bytesReceived)
    }
  })
  return bytesReceived
}
