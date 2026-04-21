import { useEffect, useRef, useCallback, useState } from 'react'

interface WebrtcPlayerProps {
  deviceId: string
  wsUrl?: string
  onConnectionStateChange?: (state: RTCPeerConnectionState) => void
  onStats?: (stats: { fps: number; bytesReceived: number }) => void
  autoPlay?: boolean
  muted?: boolean
  maxReconnectAttempts?: number
  reconnectDelay?: number
}

interface SignalingMessage {
  type: 'offer' | 'answer' | 'candidate'
  sdp?: string
  candidate?: {
    candidate: string
    sdpMid: string
    sdpMLineIndex: number
  }
}

const DEFAULT_WS_URL = '/ws/signaling'
const DEFAULT_MAX_RECONNECT_ATTEMPTS = 5
const DEFAULT_RECONNECT_DELAY = 1000
const MAX_RECONNECT_DELAY = 30000

export default function WebrtcPlayer({
  deviceId,
  wsUrl = DEFAULT_WS_URL,
  onConnectionStateChange,
  onStats,
  autoPlay = true,
  muted = true,
  maxReconnectAttempts = DEFAULT_MAX_RECONNECT_ATTEMPTS,
  reconnectDelay = DEFAULT_RECONNECT_DELAY,
}: WebrtcPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const statsIntervalRef = useRef<number | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const pendingCandidatesRef = useRef<RTCIceCandidateInit[]>([])

  const [connectionState, setConnectionState] = useState<RTCPeerConnectionState>('new')
  const [error, setError] = useState<string | null>(null)
  const [isConnected, setIsConnected] = useState(false)

  // Refs for reconnect logic (to avoid circular deps in callbacks)
  const startConnectionRef = useRef<() => Promise<void>>()

  // Handle ICE candidate
  const handleICECandidate = useCallback((event: RTCPeerConnectionIceEvent) => {
    if (event.candidate && wsRef.current) {
      const message: SignalingMessage = {
        type: 'candidate',
        candidate: {
          candidate: event.candidate.candidate,
          sdpMid: event.candidate.sdpMid || '',
          sdpMLineIndex: event.candidate.sdpMLineIndex || 0,
        },
      }
      wsRef.current.send(JSON.stringify(message))
    }
  }, [])

  // Handle track
  const handleTrack = useCallback((event: RTCTrackEvent) => {
    if (videoRef.current && event.streams[0]) {
      videoRef.current.srcObject = event.streams[0]
      if (autoPlay) {
        videoRef.current.play().catch(console.error)
      }
    }
  }, [autoPlay])

  // Handle connection state change
  const handleConnectionStateChange = useCallback(() => {
    if (pcRef.current) {
      const state = pcRef.current.connectionState
      setConnectionState(state)
      setIsConnected(state === 'connected')
      onConnectionStateChange?.(state)

      if (state === 'failed') {
        setError('Connection failed')
        // Attempt reconnect with exponential backoff
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = Math.min(reconnectDelay * Math.pow(2, reconnectAttemptsRef.current), MAX_RECONNECT_DELAY)
          console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current + 1}/${maxReconnectAttempts})`)
          reconnectTimeoutRef.current = window.setTimeout(() => {
            reconnectAttemptsRef.current++
            startConnectionRef.current?.()
          }, delay)
        } else {
          setError('Connection failed after max reconnect attempts')
        }
      } else if (state === 'disconnected') {
        // Try to reconnect on temporary disconnection
        setError('Connection lost, attempting to reconnect...')
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          const delay = Math.min(reconnectDelay * Math.pow(2, reconnectAttemptsRef.current), MAX_RECONNECT_DELAY)
          console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current + 1}/${maxReconnectAttempts})`)
          reconnectTimeoutRef.current = window.setTimeout(() => {
            reconnectAttemptsRef.current++
            stopConnection()
            startConnectionRef.current?.()
          }, delay)
        }
      } else if (state === 'connected') {
        setError(null)
        // Reset reconnect attempts on successful connection
        reconnectAttemptsRef.current = 0
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current)
          reconnectTimeoutRef.current = null
        }
      }
    }
  }, [onConnectionStateChange, maxReconnectAttempts, reconnectDelay])

  // Create peer connection
  const createPeerConnection = useCallback(async () => {
    const config: RTCConfiguration = {
      iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
      ],
    }

    const pc = new RTCPeerConnection(config)
    pcRef.current = pc

    // Set up event handlers
    pc.onicecandidate = handleICECandidate
    pc.ontrack = handleTrack
    pc.onconnectionstatechange = handleConnectionStateChange

    // Add transceiver for receiving video
    pc.addTransceiver('video', { direction: 'recvonly' })

    return pc
  }, [handleICECandidate, handleTrack, handleConnectionStateChange])

  // Handle signaling message
  const handleSignalingMessage = useCallback(async (message: SignalingMessage) => {
    const pc = pcRef.current
    if (!pc) return

    switch (message.type) {
      case 'offer':
        // We receive an offer, create an answer
        await pc.setRemoteDescription({
          type: 'offer',
          sdp: message.sdp!,
        })
        const answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        // Send answer back
        if (wsRef.current) {
          const response: SignalingMessage = {
            type: 'answer',
            sdp: answer.sdp!,
          }
          wsRef.current.send(JSON.stringify(response))
        }
        break

      case 'answer':
        // We receive an answer to our offer
        await pc.setRemoteDescription({
          type: 'answer',
          sdp: message.sdp!,
        })

        // Process any queued ICE candidates now that remote description is set
        if (pendingCandidatesRef.current.length > 0) {
          for (const candidate of pendingCandidatesRef.current) {
            try {
              await pc.addIceCandidate(candidate)
            } catch (e) {
              console.warn('Failed to add queued ICE candidate:', e)
            }
          }
          pendingCandidatesRef.current = [] // Clear queue
        }
        break

      case 'candidate':
        // Add ICE candidate
        if (message.candidate) {
          const candidateInit = {
            candidate: message.candidate.candidate,
            sdpMid: message.candidate.sdpMid,
            sdpMLineIndex: message.candidate.sdpMLineIndex,
          }

          if (pc.remoteDescription) {
            try {
              await pc.addIceCandidate(candidateInit)
            } catch (e) {
              console.warn('Failed to add ICE candidate:', e)
            }
          } else {
            // Queue candidate until remote description is set
            pendingCandidatesRef.current.push(candidateInit)
          }
        }
        break
    }
  }, [])

  // Start connection
  const startConnection = useCallback(async () => {
    try {
      setError(null)

      // Create WebSocket for signaling
      const ws = new WebSocket(`${wsUrl}/${deviceId}`)
      wsRef.current = ws

      ws.onopen = async () => {
        console.log('Signaling WebSocket connected')

        // Create peer connection
        const pc = await createPeerConnection()

        // Create and send offer
        const offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        const message: SignalingMessage = {
          type: 'offer',
          sdp: offer.sdp!,
        }
        ws.send(JSON.stringify(message))
      }

      ws.onmessage = async (event) => {
        try {
          const message: SignalingMessage = JSON.parse(event.data)
          await handleSignalingMessage(message)
        } catch (e) {
          console.error('Failed to handle signaling message:', e)
        }
      }

      ws.onerror = (e) => {
        console.error('WebSocket error:', e)
        setError('WebSocket connection error')
      }

      ws.onclose = () => {
        console.log('Signaling WebSocket closed')
      }
    } catch (e) {
      console.error('Failed to start connection:', e)
      setError('Failed to start connection')
    }
  }, [deviceId, wsUrl, createPeerConnection, handleSignalingMessage])

  // Keep ref updated for reconnect logic
  useEffect(() => {
    startConnectionRef.current = startConnection
  }, [startConnection])

  // Stop connection
  const stopConnection = useCallback(() => {
    // Clear reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    if (statsIntervalRef.current) {
      clearInterval(statsIntervalRef.current)
      statsIntervalRef.current = null
    }

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    if (pcRef.current) {
      pcRef.current.close()
      pcRef.current = null
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null
    }

    setIsConnected(false)
    setConnectionState('closed')
  }, [])

  // Collect stats
  const collectStats = useCallback(async () => {
    if (!pcRef.current || !onStats) return

    try {
      const stats = await pcRef.current.getStats()
      let bytesReceived = 0
      let fps = 0

      stats.forEach((report) => {
        if (report.type === 'inbound-rtp' && report.kind === 'video') {
          bytesReceived = report.bytesReceived || 0
          // Use framesPerSecond if available (Chrome 78+)
          fps = report.framesPerSecond || 0
        }
      })

      // Fallback: calculate FPS from framesDecoded if framesPerSecond not available
      if (fps === 0) {
        stats.forEach((report) => {
          if (report.type === 'inbound-rtp' && report.kind === 'video') {
            const framesDecoded = report.framesDecoded || 0
            // Store previous value and calculate delta
            const prevFrames = (pcRef.current as any)._prevFramesDecoded || 0
            const prevTime = (pcRef.current as any)._prevStatsTime || Date.now()
            const now = Date.now()
            const timeDelta = (now - prevTime) / 1000

            if (prevFrames > 0 && timeDelta > 0) {
              fps = Math.round((framesDecoded - prevFrames) / timeDelta)
            }

            ;(pcRef.current as any)._prevFramesDecoded = framesDecoded
            ;(pcRef.current as any)._prevStatsTime = now
          }
        })
      }

      onStats({ fps, bytesReceived })
    } catch (e) {
      console.error('Failed to collect stats:', e)
    }
  }, [onStats])

  // Start stats collection
  useEffect(() => {
    // Clear any existing interval before creating a new one
    if (statsIntervalRef.current) {
      clearInterval(statsIntervalRef.current)
      statsIntervalRef.current = null
    }

    if (isConnected && onStats) {
      statsIntervalRef.current = window.setInterval(collectStats, 1000)
    }

    return () => {
      if (statsIntervalRef.current) {
        clearInterval(statsIntervalRef.current)
        statsIntervalRef.current = null
      }
    }
  }, [isConnected, onStats, collectStats])

  // Auto-connect on mount or when props change
  useEffect(() => {
    startConnectionRef.current?.()
    return () => {
      stopConnection()
    }
  }, [deviceId, wsUrl]) // Only re-run when deviceId or wsUrl changes

  return (
    <div className="webrtc-player">
      <video
        ref={videoRef}
        autoPlay={autoPlay}
        muted={muted}
        playsInline
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          backgroundColor: '#000',
        }}
      />
      {error && (
        <div className="webrtc-error" style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          color: '#ff4d4f',
          background: 'rgba(0,0,0,0.8)',
          padding: '8px 16px',
          borderRadius: '4px',
        }}>
          {error}
        </div>
      )}
      <div className="webrtc-status" style={{
        position: 'absolute',
        top: 8,
        right: 8,
        padding: '4px 8px',
        background: 'rgba(0,0,0,0.6)',
        color: '#fff',
        borderRadius: '4px',
        fontSize: '12px',
      }}>
        <span style={{
          display: 'inline-block',
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: isConnected ? '#52c41a' : '#faad14',
          marginRight: 6,
        }} />
        {connectionState}
      </div>
    </div>
  )
}

// Export connection control functions
export type WebrtcPlayerRef = {
  start: () => void
  stop: () => void
  reconnect: () => void
}
