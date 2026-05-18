import { useCallback, useEffect, useState, type RefObject } from 'react'
import { KEYBOARD_KEY_CODE_MAP } from './api'

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false
  const tagName = target.tagName.toLowerCase()
  return tagName === 'input' || tagName === 'textarea' || target.isContentEditable
}

interface UseScreenControlsOptions {
  isPlaying: boolean
  remoteControlSupported: boolean
  isIosStaticActionSupported: boolean
  playerContainerRef: RefObject<HTMLDivElement | null>
  handleIosTouchInput: (type: string, x: number, y: number, extra?: Record<string, unknown>) => boolean
  publishControl: (payload: Record<string, unknown>, reliable?: boolean) => void
  sendAndroidKey: (keyCode: number) => void
  flushPendingMove: () => void
  scheduleMove: (x: number, y: number) => void
  sendIosText: (text: string) => Promise<boolean>
}

export default function useScreenControls({
  isPlaying,
  remoteControlSupported,
  isIosStaticActionSupported,
  playerContainerRef,
  handleIosTouchInput,
  publishControl,
  sendAndroidKey,
  flushPendingMove,
  scheduleMove,
  sendIosText,
}: UseScreenControlsOptions) {
  const [quickInputText, setQuickInputText] = useState('')
  const [virtualKeyboardOpen, setVirtualKeyboardOpen] = useState(false)

  const handleTouchInput = useCallback((type: string, x: number, y: number, extra?: Record<string, unknown>) => {
    if (handleIosTouchInput(type, x, y, extra)) return
    if (!remoteControlSupported) return
    if (type !== 'touch') return
    const action = extra?.action || 'move'
    if (action === 'move') {
      scheduleMove(x, y)
      return
    }

    flushPendingMove()
    publishControl({ type: 'touch', action, x, y }, true)
  }, [flushPendingMove, handleIosTouchInput, publishControl, remoteControlSupported, scheduleMove])

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

  const sendKey = useCallback((keycode: string) => {
    const keyMap: Record<string, number> = {
      KEYCODE_HOME: 3,
      KEYCODE_BACK: 4,
      KEYCODE_APP_SWITCH: 187,
      KEYCODE_POWER: 26,
    }

    const keyCode = keyMap[keycode]
    if (!keyCode) return
    sendAndroidKey(keyCode)
  }, [sendAndroidKey])

  const sendText = useCallback(async () => {
    const text = quickInputText
    if (!text) return

    if (isIosStaticActionSupported) {
      const success = await sendIosText(text)
      if (success) {
        setQuickInputText('')
        setVirtualKeyboardOpen(false)
      }
      return
    }

    if (!remoteControlSupported) return

    publishControl({ type: 'text', text }, true)
    setQuickInputText('')
    setVirtualKeyboardOpen(false)
  }, [isIosStaticActionSupported, publishControl, quickInputText, remoteControlSupported, sendIosText])

  const handleFullscreen = useCallback(() => {
    playerContainerRef.current?.requestFullscreen()
  }, [playerContainerRef])

  return {
    quickInputText,
    setQuickInputText,
    virtualKeyboardOpen,
    setVirtualKeyboardOpen,
    handleTouchInput,
    sendKey,
    sendText,
    handleFullscreen,
  }
}
