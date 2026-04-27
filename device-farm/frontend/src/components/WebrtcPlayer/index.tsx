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
  onStats?: (stats: { fps: number; bytesReceived: number }) => void
  onRoomCreated?: (room: Room) => void
  onFirstFrame?: () => void
}

export default function WebrtcPlayer({
  token,
  serverUrl,
  onConnectionStateChange,
  onRoomCreated,
  onFirstFrame,
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
        <VideoContainer onFirstFrame={onFirstFrame} onStats={onStats} />
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
}: {
  onFirstFrame?: () => void
  onStats?: (stats: { fps: number; bytesReceived: number }) => void
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
      const video = videoRef.current
      if (!video || typeof video.getVideoPlaybackQuality !== 'function') return

      const quality = video.getVideoPlaybackQuality()
      const now = performance.now()
      const elapsedSeconds = (now - statsRef.current.lastTime) / 1000
      const frameDelta = quality.totalVideoFrames - statsRef.current.lastFrames
      const fps = elapsedSeconds > 0 ? Math.max(0, Math.round(frameDelta / elapsedSeconds)) : 0

      statsRef.current = {
        lastFrames: quality.totalVideoFrames,
        lastTime: now,
      }
      onStats({ fps, bytesReceived: 0 })
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
        等待视频流...
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
