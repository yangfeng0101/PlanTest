/* eslint-disable react-refresh/only-export-components */
import { useCallback, useRef, useState, useEffect } from 'react'

interface TouchHandlerOptions {
  // Device screen dimensions
  screenWidth: number
  screenHeight: number
  // Callbacks
  onInput?: (type: string, x: number, y: number, extra?: Record<string, unknown>) => void
  // Gesture detection thresholds
  longPressDelay?: number // ms
  swipeThreshold?: number // pixels
  tapThreshold?: number // pixels
}

interface TouchState {
  startX: number
  startY: number
  startTime: number
  isLongPress: boolean
  isSwipe: boolean
}

interface MappedPoint {
  x: number
  y: number
  inside: boolean
}

interface UseTouchHandlerReturn {
  // Event handlers
  handlePointerDown: (e: React.PointerEvent) => void
  handlePointerMove: (e: React.PointerEvent) => void
  handlePointerUp: (e: React.PointerEvent) => void
  // State
  isPressed: boolean
  touchPoint: { x: number; y: number } | null
  gestureType: 'tap' | 'long-press' | 'swipe' | null
  // Ref setter for container
  setContainerRef: (node: HTMLDivElement | null) => void
}

export function useTouchHandler(options: TouchHandlerOptions): UseTouchHandlerReturn {
  const {
    screenWidth,
    screenHeight,
    onInput,
    longPressDelay = 800,
    swipeThreshold = 30,
    tapThreshold = 10,
  } = options

  const [isPressed, setIsPressed] = useState(false)
  const [touchPoint, setTouchPoint] = useState<{ x: number; y: number } | null>(null)
  const [gestureType, setGestureType] = useState<'tap' | 'long-press' | 'swipe' | null>(null)

  const touchStateRef = useRef<TouchState | null>(null)
  const longPressTimerRef = useRef<number | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)

  // Set container ref callback
  const setContainerRef = useCallback((node: HTMLDivElement | null) => {
    containerRef.current = node
  }, [])

  // Map coordinates from container to device screen
  const mapCoordinates = useCallback(
    (clientX: number, clientY: number, containerRect: DOMRect): MappedPoint | null => {
      if (screenWidth <= 0 || screenHeight <= 0 || containerRect.width <= 0 || containerRect.height <= 0) {
        return null
      }

      const screenRatio = screenWidth / screenHeight
      const containerRatio = containerRect.width / containerRect.height
      const renderedWidth = containerRatio > screenRatio
        ? containerRect.height * screenRatio
        : containerRect.width
      const renderedHeight = containerRatio > screenRatio
        ? containerRect.height
        : containerRect.width / screenRatio
      const offsetX = (containerRect.width - renderedWidth) / 2
      const offsetY = (containerRect.height - renderedHeight) / 2
      const rawX = clientX - containerRect.left - offsetX
      const rawY = clientY - containerRect.top - offsetY
      const inside = rawX >= 0 && rawX <= renderedWidth && rawY >= 0 && rawY <= renderedHeight

      const relativeX = Math.min(Math.max(rawX, 0), renderedWidth)
      const relativeY = Math.min(Math.max(rawY, 0), renderedHeight)

      const scaleX = screenWidth / renderedWidth
      const scaleY = screenHeight / renderedHeight

      // Map to device coordinates
      const deviceX = Math.round(relativeX * scaleX)
      const deviceY = Math.round(relativeY * scaleY)

      return { x: deviceX, y: deviceY, inside }
    },
    [screenWidth, screenHeight]
  )

  // Detect gesture type
  const detectGesture = useCallback(
    (startX: number, startY: number, endX: number, endY: number): 'tap' | 'swipe' => {
      const dx = endX - startX
      const dy = endY - startY
      const distance = Math.sqrt(dx * dx + dy * dy)

      if (distance > swipeThreshold) {
        return 'swipe'
      }
      return 'tap'
    },
    [swipeThreshold]
  )

  // Handle pointer down
  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault()
      e.stopPropagation()

      // Use container ref instead of e.target to avoid incorrect bounds from child elements
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const point = mapCoordinates(e.clientX, e.clientY, rect)
      if (!point?.inside) return
      const { x, y } = point

      touchStateRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        startTime: Date.now(),
        isLongPress: false,
        isSwipe: false,
      }

      setIsPressed(true)
      setTouchPoint({ x, y })
      setGestureType(null)

      // Send touch down
      onInput?.('touch', x, y, { action: 'down' })

      // Start long press timer
      longPressTimerRef.current = window.setTimeout(() => {
        if (touchStateRef.current) {
          touchStateRef.current.isLongPress = true
          setGestureType('long-press')
          // Send long press event
          onInput?.('long-press', x, y)
        }
      }, longPressDelay)
    },
    [mapCoordinates, onInput, longPressDelay]
  )

  // Handle pointer move
  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!touchStateRef.current || !isPressed) return

      // Use container ref instead of e.target to avoid incorrect bounds from child elements
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const point = mapCoordinates(e.clientX, e.clientY, rect)
      if (!point) return
      const { x, y } = point

      setTouchPoint({ x, y })

      // Check if moved enough to be a swipe (cancel long press)
      const dx = e.clientX - touchStateRef.current.startX
      const dy = e.clientY - touchStateRef.current.startY
      const distance = Math.sqrt(dx * dx + dy * dy)

      if (distance > tapThreshold) {
        // Cancel long press timer
        if (longPressTimerRef.current) {
          clearTimeout(longPressTimerRef.current)
          longPressTimerRef.current = null
        }
        touchStateRef.current.isSwipe = true
      }

      // Send touch move
      onInput?.('touch', x, y, { action: 'move' })
    },
    [isPressed, mapCoordinates, onInput, tapThreshold]
  )

  // Handle pointer up
  const handlePointerUp = useCallback(
    (e: React.PointerEvent) => {
      if (!touchStateRef.current) return

      // Cancel long press timer
      if (longPressTimerRef.current) {
        clearTimeout(longPressTimerRef.current)
        longPressTimerRef.current = null
      }

      // Use container ref instead of e.target to avoid incorrect bounds from child elements
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const point = mapCoordinates(e.clientX, e.clientY, rect)
      if (!point) return
      const { x, y } = point

      // Detect gesture
      if (!touchStateRef.current.isLongPress) {
        const gesture = detectGesture(
          touchStateRef.current.startX,
          touchStateRef.current.startY,
          e.clientX,
          e.clientY
        )
        setGestureType(gesture)

        if (gesture === 'swipe') {
          // Calculate swipe direction and distance
          const startX = touchStateRef.current.startX
          const startY = touchStateRef.current.startY
          const startCoords = mapCoordinates(startX, startY, rect)
          if (!startCoords) return

          // Send swipe event
          onInput?.('swipe', startCoords.x, startCoords.y, {
            endX: x,
            endY: y,
          })
        }
      }

      // Send touch up
      onInput?.('touch', x, y, { action: 'up' })

      setIsPressed(false)
      touchStateRef.current = null

      // Clear gesture type after animation
      setTimeout(() => setGestureType(null), 300)
    },
    [mapCoordinates, onInput, detectGesture]
  )

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (longPressTimerRef.current) {
        clearTimeout(longPressTimerRef.current)
      }
    }
  }, [])

  return {
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    isPressed,
    touchPoint,
    gestureType,
    setContainerRef,
  }
}

// Touch overlay component
interface TouchOverlayProps {
  screenWidth: number
  screenHeight: number
  onInput?: (type: string, x: number, y: number, extra?: Record<string, unknown>) => void
  showIndicator?: boolean
  disabled?: boolean
  children?: React.ReactNode
}

export function TouchOverlay({
  screenWidth,
  screenHeight,
  onInput,
  showIndicator = true,
  disabled = false,
  children,
}: TouchOverlayProps) {
  const { handlePointerDown, handlePointerMove, handlePointerUp, isPressed, touchPoint, gestureType, setContainerRef } =
    useTouchHandler({
      screenWidth,
      screenHeight,
      onInput,
    })

  return (
    <div
      ref={setContainerRef}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        touchAction: 'none',
        userSelect: 'none',
      }}
      onPointerDownCapture={disabled ? undefined : handlePointerDown}
      onPointerMoveCapture={disabled ? undefined : handlePointerMove}
      onPointerUpCapture={disabled ? undefined : handlePointerUp}
      onPointerCancelCapture={disabled ? undefined : handlePointerUp}
    >
      {children}

      {/* Touch indicator */}
      {showIndicator && isPressed && touchPoint && (
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            width: gestureType === 'long-press' ? 60 : 40,
            height: gestureType === 'long-press' ? 60 : 40,
            borderRadius: '50%',
            background: gestureType === 'long-press' ? 'rgba(255, 77, 79, 0.5)' : 'rgba(24, 144, 255, 0.5)',
            border: `2px solid ${gestureType === 'long-press' ? '#ff4d4f' : '#1890ff'}`,
            transform: 'translate(-50%, -50%)',
            pointerEvents: 'none',
            transition: 'all 0.15s ease',
          }}
        />
      )}

      {/* Gesture feedback */}
      {gestureType && (
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            padding: '4px 12px',
            background: 'rgba(0, 0, 0, 0.7)',
            color: '#fff',
            borderRadius: '4px',
            fontSize: '12px',
            pointerEvents: 'none',
          }}
        >
          {gestureType === 'tap' ? '点击' : gestureType === 'long-press' ? '长按' : '滑动'}
        </div>
      )}
    </div>
  )
}

export default TouchOverlay
