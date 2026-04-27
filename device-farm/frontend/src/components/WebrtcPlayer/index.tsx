import { useEffect } from 'react'
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
}

export default function WebrtcPlayer({
  token,
  serverUrl,
  onConnectionStateChange,
  onRoomCreated,
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
        <VideoContainer />
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

function VideoContainer() {
  const tracks = useTracks([Track.Source.ScreenShare, Track.Source.Camera])
  
  // We expect the agent to publish a track
  const track = tracks[0]

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
      trackRef={track}
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'contain',
        backgroundColor: '#000',
      }}
    />
  )
}
