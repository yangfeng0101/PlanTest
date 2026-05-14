import type { MouseEvent, PointerEvent, RefObject } from 'react'
import VideoCameraOutlined from '@ant-design/icons/VideoCameraOutlined'
import type { Room } from 'livekit-client'
import WebrtcPlayer from '@/components/WebrtcPlayer'
import { TouchOverlay } from '@/components/TouchHandler'
import type { RenderMetrics, UIElementNode } from './types'
import type { buildVisibleUiElements } from './uiHierarchy'

type VisibleUiElement = ReturnType<typeof buildVisibleUiElements>[number]

interface ScreenStageProps {
  playerViewportRef: RefObject<HTMLDivElement>
  playerContainerRef: RefObject<HTMLDivElement>
  playerBoxSize: { width: number; height: number } | null
  isPlaying: boolean
  isIosStaticDebug: boolean
  isIosDirectMjpegMirror: boolean
  iosMjpegStreamUrl: string
  deviceInfo: { width: number; height: number } | null
  handleTouchInput: (type: string, x: number, y: number, extra?: Record<string, unknown>) => void
  uiElements: UIElementNode[]
  visibleUiElements: VisibleUiElement[]
  selectedUiElement: UIElementNode | null
  onSelectUiElement: (element: UIElementNode) => void
  renderMetrics: RenderMetrics | null
  uiScreen: { width: number; height: number } | null
  lkSession: { url: string; token: string } | null
  selectedDevice: string
  isInitializing: boolean
  startupStatusText: string
  onIOSMJPEGLoad: () => void
  onIOSMJPEGError: () => void
  onConnectionStateChange: (state: string) => void
  onWebRTCStats: (stats: { fps: number; bytesReceived: number; latencyMs?: number }) => void
  onWebRTCFirstFrame: () => void
  onRoomCreated: (room: Room) => void
  iosTapMode: boolean
  iosSwipeMode: boolean
  onStaticStageClick: (event: MouseEvent<HTMLDivElement>) => void
  onStaticStagePointerDown: (event: PointerEvent<HTMLDivElement>) => void
  onStaticStagePointerMove: (event: PointerEvent<HTMLDivElement>) => void
  onStaticStagePointerUp: (event: PointerEvent<HTMLDivElement>) => void
  onStaticStagePointerCancel: (event: PointerEvent<HTMLDivElement>) => void
  staticScreenshot: string | null
  staticScreenshotLoading: boolean
  staticActionLoading: boolean
}

export default function ScreenStage({
  playerViewportRef,
  playerContainerRef,
  playerBoxSize,
  isPlaying,
  isIosStaticDebug,
  isIosDirectMjpegMirror,
  iosMjpegStreamUrl,
  deviceInfo,
  handleTouchInput,
  uiElements,
  visibleUiElements,
  selectedUiElement,
  onSelectUiElement,
  renderMetrics,
  uiScreen,
  lkSession,
  selectedDevice,
  isInitializing,
  startupStatusText,
  onIOSMJPEGLoad,
  onIOSMJPEGError,
  onConnectionStateChange,
  onWebRTCStats,
  onWebRTCFirstFrame,
  onRoomCreated,
  iosTapMode,
  iosSwipeMode,
  onStaticStageClick,
  onStaticStagePointerDown,
  onStaticStagePointerMove,
  onStaticStagePointerUp,
  onStaticStagePointerCancel,
  staticScreenshot,
  staticScreenshotLoading,
  staticActionLoading,
}: ScreenStageProps) {
  const uiElementOverlay = uiElements.length > 0 && renderMetrics && uiScreen ? (
    <div
      className="ui-element-layer"
      style={{
        left: renderMetrics.left,
        top: renderMetrics.top,
        width: renderMetrics.width,
        height: renderMetrics.height,
      }}
    >
      {visibleUiElements.map(({ element, bounds, zIndex }) => {
        const isSelected = selectedUiElement?.uid === element.uid
        return (
          <button
            key={element.uid}
            type="button"
            className={`ui-element-box ${isSelected ? 'selected' : ''} ${element.clickable ? 'clickable' : ''}`}
            title={element.resource_id || element.content_desc || element.text || element.class_name}
            style={{
              left: `${(bounds.left / uiScreen.width) * 100}%`,
              top: `${(bounds.top / uiScreen.height) * 100}%`,
              width: `${(bounds.width / uiScreen.width) * 100}%`,
              height: `${(bounds.height / uiScreen.height) * 100}%`,
              zIndex,
            }}
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              onSelectUiElement(element)
            }}
            onPointerDown={(event) => {
              event.stopPropagation()
            }}
          />
        )
      })}
    </div>
  ) : null

  return (
    <div ref={playerViewportRef} className="player-viewport">
      <div
        ref={playerContainerRef}
        className={`player-container ${isPlaying || isIosStaticDebug ? 'active' : ''}`}
        style={playerBoxSize ? { width: playerBoxSize.width, height: playerBoxSize.height } : undefined}
      >
        {isPlaying && isIosDirectMjpegMirror && iosMjpegStreamUrl ? (
          <TouchOverlay
            screenWidth={deviceInfo?.width || 1080}
            screenHeight={deviceInfo?.height || 1920}
            onInput={handleTouchInput}
            disabled={uiElements.length > 0}
          >
            <img
              className="static-debug-screenshot ios-mjpeg-stream"
              src={iosMjpegStreamUrl}
              alt="iOS MJPEG direct stream"
              onLoad={onIOSMJPEGLoad}
              onError={onIOSMJPEGError}
            />
            {isInitializing && (
              <div className="video-waiting-overlay">
                <div className="video-waiting-content">
                  <span>{startupStatusText}</span>
                </div>
              </div>
            )}
            {uiElementOverlay}
          </TouchOverlay>
        ) : isPlaying && lkSession ? (
          <TouchOverlay
            screenWidth={deviceInfo?.width || 1080}
            screenHeight={deviceInfo?.height || 1920}
            onInput={handleTouchInput}
            disabled={uiElements.length > 0}
          >
            <WebrtcPlayer
              deviceId={selectedDevice}
              token={lkSession.token}
              serverUrl={lkSession.url}
              waitingText={isInitializing ? startupStatusText : ''}
              onConnectionStateChange={onConnectionStateChange}
              onStats={onWebRTCStats}
              onFirstFrame={onWebRTCFirstFrame}
              onRoomCreated={onRoomCreated}
            />
            {isInitializing && (
              <div className="video-waiting-overlay">
                <div className="video-waiting-content">
                  <span>{startupStatusText}</span>
                </div>
              </div>
            )}
            {uiElementOverlay}
          </TouchOverlay>
        ) : isIosStaticDebug ? (
          <div
            className={`static-debug-stage ${iosTapMode ? 'tap-mode' : ''} ${iosSwipeMode ? 'swipe-mode' : ''}`}
            onClick={onStaticStageClick}
            onPointerDown={onStaticStagePointerDown}
            onPointerMove={onStaticStagePointerMove}
            onPointerUp={onStaticStagePointerUp}
            onPointerCancel={onStaticStagePointerCancel}
          >
            {staticScreenshot ? (
              <img className="static-debug-screenshot" src={staticScreenshot} alt="iOS static screenshot" />
            ) : (
              <div className="player-placeholder static-debug-placeholder">
                <VideoCameraOutlined style={{ fontSize: 48, marginBottom: 12 }} />
                <p>iOS 静态预览</p>
                <span>刷新截图或获取控件后查看当前页面</span>
              </div>
            )}
            {staticScreenshotLoading && (
              <div className="video-waiting-overlay">
                <div className="video-waiting-content">
                  <span>正在刷新截图...</span>
                </div>
              </div>
            )}
            {staticActionLoading && !staticScreenshotLoading && (
              <div className="video-waiting-overlay translucent">
                <div className="video-waiting-content">
                  <span>正在执行静态操作...</span>
                </div>
              </div>
            )}
            {uiElementOverlay}
          </div>
        ) : (
          <div className="player-placeholder">
            <VideoCameraOutlined style={{ fontSize: 56, marginBottom: 16 }} />
            <p>从设备管理选择设备后点击连接开始投屏</p>
          </div>
        )}
      </div>
    </div>
  )
}
