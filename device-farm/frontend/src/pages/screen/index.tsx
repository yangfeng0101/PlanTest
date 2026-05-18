import { useState, useCallback } from 'react'
import { formatDeviceOs } from '@/utils/device'
import type { WorkspaceTab } from './types'
import DeviceStagePanel from './DeviceStagePanel'
import WorkspacePanel from './WorkspacePanel'
import ScriptModals from './ScriptModals'
import useScreenDevices from './useScreenDevices'
import useIosDebugActions from './useIosDebugActions'
import useScreenSession from './useScreenSession'
import useScreenScriptWorkspace from './useScreenScriptWorkspace'
import useScreenUiHierarchy from './useScreenUiHierarchy'
import useScreenLayoutMetrics from './useScreenLayoutMetrics'
import useScreenControls from './useScreenControls'
import useScreenMode from './useScreenMode'
import './ScreenPage.css'

export default function ScreenPage() {
  const {
    devicesLoaded,
    selectedDevice,
    currentDevice,
    deviceInfo,
    setDeviceInfo,
  } = useScreenDevices()
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<WorkspaceTab>('inspect')
  const {
    screenMirrorSupported,
    remoteControlSupported,
    uiHierarchySupported,
    screenshotSupported,
    isIosDevice,
    isIosDirectMjpegMirror,
    isIosLivePreview,
    isIosStaticDebug,
    isIosStaticActionSupported,
    iosModeLabel,
  } = useScreenMode(currentDevice)

  const {
    uiElements,
    selectedUiElement,
    setSelectedUiElement,
    loadingUiHierarchy,
    uiScreen,
    setUiScreen,
    clearUiHierarchy,
    applyUiScreen,
    fetchUiHierarchy,
    visibleUiElements,
    locatorSnippets,
  } = useScreenUiHierarchy({
    selectedDevice,
    currentDevice,
    isIosDevice,
    isIosStaticDebug,
    isIosDirectMjpegMirror,
    setDeviceInfo,
  })

  const {
    playerViewportRef,
    playerContainerRef,
    playerBoxSize,
    renderMetrics,
  } = useScreenLayoutMetrics(deviceInfo)

  const {
    staticScreenshot,
    staticScreenshotLoading,
    staticActionLoading,
    iosTapMode,
    setIosTapMode,
    iosSwipeMode,
    setIosSwipeMode,
    staticAutoRefresh,
    setStaticAutoRefresh,
    staticAutoRefreshIntervalMs,
    setStaticAutoRefreshIntervalMs,
    staticRefreshDurationMs,
    staticRefreshFailures,
    staticRefreshLastError,
    staticDebugSessionActive,
    setStaticDebugSessionActive,
    staticPointerPoint,
    lastStaticAction,
    lastIosControlStatus,
    refreshStaticScreenshot,
    handleTouchInput: handleIosTouchInput,
    handleStaticStageClick,
    handleStaticStagePointerDown,
    handleStaticStagePointerMove,
    handleStaticStagePointerUp,
    handleStaticStagePointerCancel,
    tapSelectedUiElement,
    longPressSelectedUiElement,
    sendIosText,
    clearStaticText,
    resetStaticDebugState,
  } = useIosDebugActions({
    selectedDevice,
    isIosStaticDebug,
    isIosDirectMjpegMirror,
    isIosLivePreview,
    isIosStaticActionSupported,
    renderMetrics,
    uiScreen,
    loadingUiHierarchy,
    selectedUiElement,
    setUiScreen,
    setDeviceInfo,
  })

  const handleStopSessionCleanup = useCallback(() => {
    clearUiHierarchy()
    resetStaticDebugState()
  }, [clearUiHierarchy, resetStaticDebugState])

  const {
    isPlaying,
    loading,
    fps,
    hasVideoFrame,
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
    handleWebRTCFirstFrame,
    handleRoomCreated,
  } = useScreenSession({
    selectedDevice,
    devicesLoaded,
    currentDevice,
    isIosDevice,
    isIosLivePreview,
    isIosStaticDebug,
    isIosDirectMjpegMirror,
    remoteControlSupported,
    onIosLogicalScreen: applyUiScreen,
    onVideoScreen: setDeviceInfo,
    onStopCleanup: handleStopSessionCleanup,
  })

  const {
    quickInputText,
    setQuickInputText,
    virtualKeyboardOpen,
    setVirtualKeyboardOpen,
    handleTouchInput,
    sendKey,
    sendText,
    handleFullscreen,
  } = useScreenControls({
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
  })

  const handleFetchUiHierarchy = useCallback(() => {
    void fetchUiHierarchy({
      isPlaying,
      refreshStaticScreenshot,
      setStaticDebugSessionActive,
    })
  }, [fetchUiHierarchy, isPlaying, refreshStaticScreenshot, setStaticDebugSessionActive])

  const openScriptWorkspace = useCallback(() => {
    setActiveWorkspaceTab('script')
  }, [])
  const {
    scriptSaving,
    scriptSaveModalOpen,
    scriptPickerOpen,
    scriptPickerLoading,
    savedScripts,
    scriptName,
    setScriptName,
    scriptDescription,
    setScriptDescription,
    scriptTags,
    setScriptTags,
    scriptContent,
    debugTask,
    debugSubmitting,
    debugCanceling,
    scriptLineCount,
    visibleDebugLogs,
    debugScreenshots,
    debugTaskActive,
    activeDebugLine,
    failedDebugLine,
    updateScriptContent,
    openScriptPicker,
    closeScriptPicker,
    selectSavedScript,
    createExampleScript,
    activateScriptWriter,
    appendScriptSnippet,
    openSaveScriptModal,
    closeSaveScriptModal,
    saveScript,
    runDebugScript,
    cancelDebugTask,
  } = useScreenScriptWorkspace({
    selectedDevice,
    currentDevice,
    selectedUiElement,
    uiElements,
    screenSessionActive: isPlaying,
    onOpenScriptWorkspace: openScriptWorkspace,
    onIosDebugSessionReleased: () => setStaticDebugSessionActive(false),
  })
  const inspectReady = isPlaying || isIosStaticDebug
  const isIosTextInputAvailable = Boolean(isIosStaticActionSupported && (isIosStaticDebug || isPlaying))
  const startupStatusText = '正在初始化设备，请稍后...'

  return (
    <div className="screen-page">
      <div className="screen-workbench">
        <DeviceStagePanel
          deviceTitle={currentDevice?.name || selectedDevice || '未选择设备'}
          deviceOsLabel={currentDevice ? formatDeviceOs(currentDevice) : ''}
          hasCurrentDevice={Boolean(currentDevice)}
          statusDotClassName={statusDotClassName}
          statusLabel={isIosStaticDebug ? '静态预览' : hasStartupError ? '连接失败' : hasVideoFrame ? '连接成功' : '连接中'}
          isPlaying={isPlaying}
          loading={loading}
          selectedDevice={selectedDevice}
          screenMirrorSupported={screenMirrorSupported}
          onToggleSession={() => isPlaying ? stopSession() : startSession()}
          playerViewportRef={playerViewportRef}
          playerContainerRef={playerContainerRef}
          playerBoxSize={playerBoxSize}
          isIosStaticDebug={isIosStaticDebug}
          isIosDirectMjpegMirror={isIosDirectMjpegMirror}
          iosMjpegStreamUrl={iosMjpegStreamUrl}
          deviceInfo={deviceInfo}
          handleTouchInput={handleTouchInput}
          uiElements={uiElements}
          visibleUiElements={visibleUiElements}
          selectedUiElement={selectedUiElement}
          onSelectUiElement={setSelectedUiElement}
          renderMetrics={renderMetrics}
          uiScreen={uiScreen}
          lkSession={lkSession}
          isInitializing={isInitializing}
          startupStatusText={startupStatusText}
          onIOSMJPEGLoad={handleIOSMJPEGLoad}
          onIOSMJPEGError={handleIOSMJPEGError}
          onConnectionStateChange={handleConnectionStateChange}
          onWebRTCStats={handleWebRTCStats}
          onWebRTCFirstFrame={handleWebRTCFirstFrame}
          onRoomCreated={handleRoomCreated}
          iosTapMode={iosTapMode}
          iosSwipeMode={iosSwipeMode}
          onStaticStageClick={handleStaticStageClick}
          onStaticStagePointerDown={handleStaticStagePointerDown}
          onStaticStagePointerMove={handleStaticStagePointerMove}
          onStaticStagePointerUp={handleStaticStagePointerUp}
          onStaticStagePointerCancel={handleStaticStagePointerCancel}
          staticScreenshot={staticScreenshot}
          staticScreenshotLoading={staticScreenshotLoading}
          staticActionLoading={staticActionLoading}
          remoteControlSupported={remoteControlSupported}
          onSendKey={sendKey}
          onFullscreen={handleFullscreen}
          virtualKeyboardOpen={virtualKeyboardOpen}
          onVirtualKeyboardOpenChange={setVirtualKeyboardOpen}
          quickInputText={quickInputText}
          onQuickInputTextChange={setQuickInputText}
          onSendText={() => { void sendText() }}
          onClearStaticText={() => { void clearStaticText() }}
          isIosTextInputAvailable={isIosTextInputAvailable}
          isIosStaticActionSupported={isIosStaticActionSupported}
          iosModeLabel={iosModeLabel}
          staticAutoRefresh={staticAutoRefresh}
          staticAutoRefreshIntervalMs={staticAutoRefreshIntervalMs}
          staticRefreshDurationMs={staticRefreshDurationMs}
          staticRefreshFailures={staticRefreshFailures}
          staticDebugSessionActive={staticDebugSessionActive}
          staticPointerPoint={staticPointerPoint}
          lastStaticAction={lastStaticAction}
          staticRefreshLastError={staticRefreshLastError}
          fps={fps}
          networkLatencyMs={networkLatencyMs}
          browserFirstFrameMs={browserFirstFrameMs}
          lastIosControlStatus={lastIosControlStatus}
        />

        <WorkspacePanel
          activeWorkspaceTab={activeWorkspaceTab}
          onOpenInspect={() => setActiveWorkspaceTab('inspect')}
          onOpenScript={activateScriptWriter}
          onOpenLogcat={() => setActiveWorkspaceTab('logcat')}
          selectedDevice={selectedDevice}
          inspectReady={inspectReady}
          uiHierarchySupported={uiHierarchySupported}
          loadingUiHierarchy={loadingUiHierarchy}
          onFetchUiHierarchy={handleFetchUiHierarchy}
          isIosStaticDebug={isIosStaticDebug}
          screenshotSupported={screenshotSupported}
          staticScreenshotLoading={staticScreenshotLoading}
          onRefreshScreenshot={() => { void refreshStaticScreenshot(false) }}
          staticAutoRefresh={staticAutoRefresh}
          staticAutoRefreshIntervalMs={staticAutoRefreshIntervalMs}
          staticScreenshot={staticScreenshot}
          staticActionLoading={staticActionLoading}
          onStaticAutoRefreshChange={setStaticAutoRefresh}
          onStaticAutoRefreshIntervalChange={setStaticAutoRefreshIntervalMs}
          isIosStaticActionSupported={isIosStaticActionSupported}
          iosTapMode={iosTapMode}
          iosSwipeMode={iosSwipeMode}
          onIosTapModeChange={(checked) => {
            setIosTapMode(checked)
            if (checked) setIosSwipeMode(false)
          }}
          onIosSwipeModeChange={(checked) => {
            setIosSwipeMode(checked)
            if (checked) setIosTapMode(false)
          }}
          selectedUiElement={selectedUiElement}
          uiElements={uiElements}
          onTapSelectedUiElement={tapSelectedUiElement}
          onLongPressSelectedUiElement={longPressSelectedUiElement}
          onClearUiHierarchy={clearUiHierarchy}
          currentDeviceLabel={currentDevice?.name || selectedDevice || '-'}
          debugTaskActive={debugTaskActive}
          debugCanceling={debugCanceling}
          debugSubmitting={debugSubmitting}
          onOpenScriptPicker={openScriptPicker}
          onCancelDebugTask={cancelDebugTask}
          onRunDebugScript={runDebugScript}
          onOpenSaveScriptModal={openSaveScriptModal}
          scriptContent={scriptContent}
          onScriptContentChange={updateScriptContent}
          activeDebugLine={activeDebugLine}
          failedDebugLine={failedDebugLine}
          scriptLineCount={scriptLineCount}
          debugTask={debugTask}
          visibleDebugLogs={visibleDebugLogs}
          debugScreenshots={debugScreenshots}
          locatorSnippets={locatorSnippets}
          onAppendScriptSnippet={appendScriptSnippet}
        />
      </div>

      <ScriptModals
        pickerOpen={scriptPickerOpen}
        pickerLoading={scriptPickerLoading}
        savedScripts={savedScripts}
        onClosePicker={closeScriptPicker}
        onCreateExampleScript={createExampleScript}
        onSelectSavedScript={selectSavedScript}
        saveOpen={scriptSaveModalOpen}
        saving={scriptSaving}
        scriptName={scriptName}
        scriptTags={scriptTags}
        scriptDescription={scriptDescription}
        onScriptNameChange={setScriptName}
        onScriptTagsChange={setScriptTags}
        onScriptDescriptionChange={setScriptDescription}
        onSaveScript={saveScript}
        onCloseSave={closeSaveScriptModal}
      />
    </div>
  )
}
