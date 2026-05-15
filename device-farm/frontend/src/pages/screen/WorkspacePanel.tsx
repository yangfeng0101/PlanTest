import { Typography } from 'antd'
import type { Task, TaskLogEntry } from '@/types'
import type { LocatorSnippet, UIElementNode, WorkspaceTab } from './types'
import InspectorPanel from './InspectorPanel'
import ScriptWorkspacePanel from './ScriptWorkspacePanel'

const { Text } = Typography

interface WorkspacePanelProps {
  activeWorkspaceTab: WorkspaceTab
  onOpenInspect: () => void
  onOpenScript: () => void
  onOpenLogcat: () => void
  selectedDevice: string
  inspectReady: boolean
  uiHierarchySupported: boolean
  loadingUiHierarchy: boolean
  onFetchUiHierarchy: () => void
  isIosStaticDebug: boolean
  screenshotSupported: boolean
  staticScreenshotLoading: boolean
  onRefreshScreenshot: () => void
  staticAutoRefresh: boolean
  staticAutoRefreshIntervalMs: number
  staticScreenshot: string | null
  staticActionLoading: boolean
  onStaticAutoRefreshChange: (checked: boolean) => void
  onStaticAutoRefreshIntervalChange: (value: number) => void
  isIosStaticActionSupported: boolean
  iosTapMode: boolean
  iosSwipeMode: boolean
  onIosTapModeChange: (checked: boolean) => void
  onIosSwipeModeChange: (checked: boolean) => void
  selectedUiElement: UIElementNode | null
  uiElements: UIElementNode[]
  onTapSelectedUiElement: () => void
  onLongPressSelectedUiElement: () => void
  onClearUiHierarchy: () => void
  currentDeviceLabel: string
  debugTaskActive: boolean
  debugCanceling: boolean
  debugSubmitting: boolean
  onOpenScriptPicker: () => void
  onCancelDebugTask: () => void
  onRunDebugScript: () => void
  onOpenSaveScriptModal: () => void
  scriptContent: string
  onScriptContentChange: (value: string) => void
  activeDebugLine: number | null
  failedDebugLine: number | null
  scriptLineCount: number
  debugTask: Task | null
  visibleDebugLogs: TaskLogEntry[]
  debugScreenshots: string[]
  locatorSnippets: LocatorSnippet[]
  onAppendScriptSnippet: (snippet: LocatorSnippet) => void
}

export default function WorkspacePanel({
  activeWorkspaceTab,
  onOpenInspect,
  onOpenScript,
  onOpenLogcat,
  selectedDevice,
  inspectReady,
  uiHierarchySupported,
  loadingUiHierarchy,
  onFetchUiHierarchy,
  isIosStaticDebug,
  screenshotSupported,
  staticScreenshotLoading,
  onRefreshScreenshot,
  staticAutoRefresh,
  staticAutoRefreshIntervalMs,
  staticScreenshot,
  staticActionLoading,
  onStaticAutoRefreshChange,
  onStaticAutoRefreshIntervalChange,
  isIosStaticActionSupported,
  iosTapMode,
  iosSwipeMode,
  onIosTapModeChange,
  onIosSwipeModeChange,
  selectedUiElement,
  uiElements,
  onTapSelectedUiElement,
  onLongPressSelectedUiElement,
  onClearUiHierarchy,
  currentDeviceLabel,
  debugTaskActive,
  debugCanceling,
  debugSubmitting,
  onOpenScriptPicker,
  onCancelDebugTask,
  onRunDebugScript,
  onOpenSaveScriptModal,
  scriptContent,
  onScriptContentChange,
  activeDebugLine,
  failedDebugLine,
  scriptLineCount,
  debugTask,
  visibleDebugLogs,
  debugScreenshots,
  locatorSnippets,
  onAppendScriptSnippet,
}: WorkspacePanelProps) {
  return (
    <section className="screen-workspace">
      <div className="workspace-tabs">
        <button
          type="button"
          className={`workspace-tab ${activeWorkspaceTab === 'inspect' ? 'active' : ''}`}
          onClick={onOpenInspect}
        >
          控件检查
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeWorkspaceTab === 'script' ? 'active' : ''}`}
          onClick={onOpenScript}
        >
          编写脚本
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeWorkspaceTab === 'logcat' ? 'active' : ''}`}
          onClick={onOpenLogcat}
        >
          Logcat
        </button>
      </div>

      {activeWorkspaceTab === 'inspect' && (
        <InspectorPanel
          selectedDevice={selectedDevice}
          inspectReady={inspectReady}
          uiHierarchySupported={uiHierarchySupported}
          loadingUiHierarchy={loadingUiHierarchy}
          onFetchUiHierarchy={onFetchUiHierarchy}
          isIosStaticDebug={isIosStaticDebug}
          screenshotSupported={screenshotSupported}
          staticScreenshotLoading={staticScreenshotLoading}
          onRefreshScreenshot={onRefreshScreenshot}
          staticAutoRefresh={staticAutoRefresh}
          staticAutoRefreshIntervalMs={staticAutoRefreshIntervalMs}
          staticScreenshot={staticScreenshot}
          staticActionLoading={staticActionLoading}
          onStaticAutoRefreshChange={onStaticAutoRefreshChange}
          onStaticAutoRefreshIntervalChange={onStaticAutoRefreshIntervalChange}
          isIosStaticActionSupported={isIosStaticActionSupported}
          iosTapMode={iosTapMode}
          iosSwipeMode={iosSwipeMode}
          onIosTapModeChange={onIosTapModeChange}
          onIosSwipeModeChange={onIosSwipeModeChange}
          selectedUiElement={selectedUiElement}
          uiElements={uiElements}
          onTapSelectedUiElement={onTapSelectedUiElement}
          onLongPressSelectedUiElement={onLongPressSelectedUiElement}
          onClearUiHierarchy={onClearUiHierarchy}
          currentDeviceLabel={currentDeviceLabel}
        />
      )}

      {activeWorkspaceTab === 'script' && (
        <ScriptWorkspacePanel
          debugTaskActive={debugTaskActive}
          debugCanceling={debugCanceling}
          debugSubmitting={debugSubmitting}
          onOpenScriptPicker={onOpenScriptPicker}
          onCancelDebugTask={onCancelDebugTask}
          onRunDebugScript={onRunDebugScript}
          onOpenSaveScriptModal={onOpenSaveScriptModal}
          scriptContent={scriptContent}
          onScriptContentChange={onScriptContentChange}
          activeDebugLine={activeDebugLine}
          failedDebugLine={failedDebugLine}
          scriptLineCount={scriptLineCount}
          debugTask={debugTask}
          visibleDebugLogs={visibleDebugLogs}
          debugScreenshots={debugScreenshots}
          selectedUiElement={selectedUiElement}
          locatorSnippets={locatorSnippets}
          onAppendScriptSnippet={onAppendScriptSnippet}
        />
      )}

      {activeWorkspaceTab === 'logcat' && (
        <div className="workspace-panel logcat-panel">
          <div className="workspace-toolbar compact">
            <Text strong>Logcat</Text>
          </div>
          <div className="logcat-placeholder">
            <Text type="secondary">Logcat 能力待接入。</Text>
          </div>
        </div>
      )}
    </section>
  )
}
