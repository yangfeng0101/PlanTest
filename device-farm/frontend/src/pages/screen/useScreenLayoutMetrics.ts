import { useEffect, useRef, useState } from 'react'
import type { RenderMetrics } from './types'

interface ScreenSize {
  width: number
  height: number
}

export default function useScreenLayoutMetrics(deviceInfo: ScreenSize | null) {
  const playerViewportRef = useRef<HTMLDivElement>(null)
  const playerContainerRef = useRef<HTMLDivElement>(null)
  const [playerBoxSize, setPlayerBoxSize] = useState<ScreenSize | null>(null)
  const [renderMetrics, setRenderMetrics] = useState<RenderMetrics | null>(null)

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
  }, [deviceInfo])

  useEffect(() => {
    const viewport = playerViewportRef.current
    if (!viewport || !deviceInfo) {
      setPlayerBoxSize(null)
      return
    }

    const updateBoxSize = () => {
      const rect = viewport.getBoundingClientRect()
      if (rect.width <= 0 || rect.height <= 0) {
        setPlayerBoxSize(null)
        return
      }

      const screenRatio = deviceInfo.width / deviceInfo.height
      const viewportRatio = rect.width / rect.height
      const height = viewportRatio > screenRatio ? rect.height : rect.width / screenRatio
      const width = viewportRatio > screenRatio ? rect.height * screenRatio : rect.width

      setPlayerBoxSize({ width, height })
    }

    updateBoxSize()
    const observer = new ResizeObserver(updateBoxSize)
    observer.observe(viewport)
    window.addEventListener('resize', updateBoxSize)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', updateBoxSize)
    }
  }, [deviceInfo])

  return {
    playerViewportRef,
    playerContainerRef,
    playerBoxSize,
    renderMetrics,
  }
}
