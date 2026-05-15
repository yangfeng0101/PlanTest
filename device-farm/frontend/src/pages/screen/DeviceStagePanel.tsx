import type { MouseEvent, PointerEvent, RefObject } from 'react'
import { Button, Input, Popover, Typography } from 'antd'
import PlayCircleOutlined from '@ant-design/icons/PlayCircleOutlined'
import PauseCircleOutlined from '@ant-design/icons/PauseCircleOutlined'
import FullscreenOutlined from '@ant-design/icons/FullscreenOutlined'
import VideoCameraOutlined from '@ant-design/icons/VideoCameraOutlined'
import HomeOutlined from '@ant-design/icons/HomeOutlined'
import RollbackOutlined from '@ant-design/icons/RollbackOutlined'
import AppstoreOutlined from '@ant-design/icons/AppstoreOutlined'
import KeyOutlined from '@ant-design/icons/KeyOutlined'
import SendOutlined from '@ant-design/icons/SendOutlined'
import DeleteOutlined from '@ant-design/icons/DeleteOutlined'
import type { Room } from 'livekit-client'
import ScreenStage from './ScreenStage'
import type { RenderMetrics, UIElementNode } from './types'
import type { buildVisibleUiElements } from './uiHierarchy'

const { Text } = Typography

type VisibleUiElement = ReturnType<typeof buildVisibleUiElements>[number]

interface DeviceStagePanelProps {
  deviceTitle: string
  deviceOsLabel: string
  hasCurrentDevice: boolean
  statusDotClassName: string
  statusLabel: string
  isPlaying: boolean
  loading: boolean
  selectedDevice: string
  screenMirrorSupported: boolean
  onToggleSession: () => void
  playerViewportRef: RefObject<HTMLDivElement>
  playerContainerRef: RefObject<HTMLDivElement>
  playerBoxSize: { width: number; height: number } | null
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
  remoteControlSupported: boolean
  onSendKey: (keycode: string) => void
  onFullscreen: () => void
  virtualKeyboardOpen: boolean
  onVirtualKeyboardOpenChange: (open: boolean) => void
  quickInputText: string
  onQuickInputTextChange: (value: string) => void
  onSendText: () => void
  onClearStaticText: () => void
  isIosTextInputAvailable: boolean
  isIosStaticActionSupported: boolean
  iosModeLabel: string
  staticAutoRefresh: boolean
  staticAutoRefreshIntervalMs: number
  staticRefreshDurationMs: number | null
  staticRefreshFailures: number
  staticDebugSessionActive: boolean
  staticPointerPoint: { x: number; y: number } | null
  lastStaticAction: string
  staticRefreshLastError: string
  fps: number
  networkLatencyMs: number | null
  browserFirstFrameMs: number | null
  lastIosControlStatus: string
}

export default function DeviceStagePanel({
  deviceTitle,
  deviceOsLabel,
  hasCurrentDevice,
  statusDotClassName,
  statusLabel,
  isPlaying,
  loading,
  selectedDevice,
  screenMirrorSupported,
  onToggleSession,
  playerViewportRef,
  playerContainerRef,
  playerBoxSize,
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
  remoteControlSupported,
  onSendKey,
  onFullscreen,
  virtualKeyboardOpen,
  onVirtualKeyboardOpenChange,
  quickInputText,
  onQuickInputTextChange,
  onSendText,
  onClearStaticText,
  isIosTextInputAvailable,
  isIosStaticActionSupported,
  iosModeLabel,
  staticAutoRefresh,
  staticAutoRefreshIntervalMs,
  staticRefreshDurationMs,
  staticRefreshFailures,
  staticDebugSessionActive,
  staticPointerPoint,
  lastStaticAction,
  staticRefreshLastError,
  fps,
  networkLatencyMs,
  browserFirstFrameMs,
  lastIosControlStatus,
}: DeviceStagePanelProps) {
  const virtualKeyboardContent = (
    <div className="virtual-keyboard-panel">
      <Input.Password
        value={quickInputText}
        onChange={(event) => onQuickInputTextChange(event.target.value)}
        onPressEnter={() => { onSendText() }}
        placeholder={isIosStaticDebug ? '先点输入框，再输入文本' : '输入文本或密码'}
        autoComplete="off"
        disabled={!((isPlaying && remoteControlSupported) || isIosTextInputAvailable)}
      />
      <Button
        type="primary"
        icon={<SendOutlined />}
        disabled={!quickInputText || !((isPlaying && remoteControlSupported) || isIosTextInputAvailable)}
        loading={isIosTextInputAvailable && staticActionLoading}
        onClick={onSendText}
      >
        输入
      </Button>
      {isIosStaticDebug && isIosStaticActionSupported && (
        <Button
          icon={<DeleteOutlined />}
          disabled={staticActionLoading}
          loading={staticActionLoading && !quickInputText}
          onClick={onClearStaticText}
        >
          清空
        </Button>
      )}
      {isIosStaticDebug && isIosStaticActionSupported && (
        <Text type="secondary" className="static-debug-input-tip">输入前先点按目标输入框获取焦点</Text>
      )}
    </div>
  )

  return (
    <section className="device-stage">
      <div className="device-stage-header">
        <div className="device-context">
          <VideoCameraOutlined />
          <span>{deviceTitle}</span>
          {hasCurrentDevice && <Text type="secondary">{deviceOsLabel}</Text>}
          <span
            className={`connection-status-dot ${statusDotClassName}`}
            aria-label={statusLabel}
            title={statusLabel}
          />
        </div>
        <Button
          type={isPlaying ? 'default' : 'primary'}
          icon={isPlaying ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
          onClick={onToggleSession}
          disabled={!selectedDevice || !screenMirrorSupported}
          loading={loading}
        >
          {loading ? '连接中' : isPlaying ? '断开' : '重新连接'}
        </Button>
      </div>

      <div className="device-frame-wrap">
        <ScreenStage
          playerViewportRef={playerViewportRef}
          playerContainerRef={playerContainerRef}
          playerBoxSize={playerBoxSize}
          isPlaying={isPlaying}
          isIosStaticDebug={isIosStaticDebug}
          isIosDirectMjpegMirror={isIosDirectMjpegMirror}
          iosMjpegStreamUrl={iosMjpegStreamUrl}
          deviceInfo={deviceInfo}
          handleTouchInput={handleTouchInput}
          uiElements={uiElements}
          visibleUiElements={visibleUiElements}
          selectedUiElement={selectedUiElement}
          onSelectUiElement={onSelectUiElement}
          renderMetrics={renderMetrics}
          uiScreen={uiScreen}
          lkSession={lkSession}
          selectedDevice={selectedDevice}
          isInitializing={isInitializing}
          startupStatusText={startupStatusText}
          onIOSMJPEGLoad={onIOSMJPEGLoad}
          onIOSMJPEGError={onIOSMJPEGError}
          onConnectionStateChange={onConnectionStateChange}
          onWebRTCStats={onWebRTCStats}
          onWebRTCFirstFrame={onWebRTCFirstFrame}
          onRoomCreated={onRoomCreated}
          iosTapMode={iosTapMode}
          iosSwipeMode={iosSwipeMode}
          onStaticStageClick={onStaticStageClick}
          onStaticStagePointerDown={onStaticStagePointerDown}
          onStaticStagePointerMove={onStaticStagePointerMove}
          onStaticStagePointerUp={onStaticStagePointerUp}
          onStaticStagePointerCancel={onStaticStagePointerCancel}
          staticScreenshot={staticScreenshot}
          staticScreenshotLoading={staticScreenshotLoading}
          staticActionLoading={staticActionLoading}
        />

        <div className="device-rail">
          <Button shape="circle" icon={<HomeOutlined />} disabled={!remoteControlSupported} onClick={() => onSendKey('KEYCODE_HOME')} />
          <Button shape="circle" icon={<RollbackOutlined />} disabled={!remoteControlSupported} onClick={() => onSendKey('KEYCODE_BACK')} />
          <Button shape="circle" icon={<AppstoreOutlined />} disabled={!remoteControlSupported} onClick={() => onSendKey('KEYCODE_APP_SWITCH')} />
          <Button shape="circle" icon={<FullscreenOutlined />} onClick={onFullscreen} />
          <Popover
            content={virtualKeyboardContent}
            trigger="click"
            placement="left"
            open={virtualKeyboardOpen}
            onOpenChange={onVirtualKeyboardOpenChange}
          >
            <Button
              shape="circle"
              type={virtualKeyboardOpen ? 'primary' : 'default'}
              icon={<KeyOutlined />}
              disabled={!((isPlaying && remoteControlSupported) || isIosTextInputAvailable)}
              aria-label="电脑键盘输入"
              title="电脑键盘输入"
            />
          </Popover>
        </div>
      </div>

      <div className="device-stage-footer">
        {isIosStaticDebug ? (
          <>
            <Text type="secondary">模式：{iosModeLabel}</Text>
            <Text type="secondary">控件：{uiElements.length}</Text>
            <Text type="secondary">连续触控：未开启</Text>
            <Text type="secondary">
              自动刷新：{staticAutoRefresh ? `${staticAutoRefreshIntervalMs / 1000}s` : '关闭'}
            </Text>
            <Text type="secondary">
              刷新：{staticRefreshDurationMs !== null ? `${staticRefreshDurationMs}ms` : '--'}
            </Text>
            <Text type={staticRefreshFailures > 0 ? 'danger' : 'secondary'}>失败：{staticRefreshFailures}</Text>
            <Text type={staticDebugSessionActive ? 'warning' : 'secondary'}>
              Session：{staticDebugSessionActive ? '占用中' : '未占用'}
            </Text>
            <Text type="secondary">
              坐标：{staticPointerPoint ? `${staticPointerPoint.x}, ${staticPointerPoint.y}` : '--'}
            </Text>
            <Text type="secondary">最近：{lastStaticAction}</Text>
            {staticRefreshLastError && (
              <Text type="danger" title={staticRefreshLastError}>错误：{staticRefreshLastError}</Text>
            )}
          </>
        ) : (
          <>
            <Text type="secondary">FPS：{isIosDirectMjpegMirror ? '直连' : fps}</Text>
            <Text type="secondary">网络延迟：{networkLatencyMs !== null ? `${networkLatencyMs}ms` : '--'}</Text>
            <Text type="secondary">首帧：{browserFirstFrameMs !== null ? `${browserFirstFrameMs}ms` : '--'}</Text>
            {isIosDirectMjpegMirror && (
              <Text type="secondary">触控：{lastIosControlStatus}</Text>
            )}
          </>
        )}
      </div>
    </section>
  )
}
