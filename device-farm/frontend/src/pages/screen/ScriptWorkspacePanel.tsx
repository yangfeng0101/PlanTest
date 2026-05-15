import PauseCircleOutlined from '@ant-design/icons/PauseCircleOutlined'
import PlayCircleOutlined from '@ant-design/icons/PlayCircleOutlined'
import DeleteOutlined from '@ant-design/icons/DeleteOutlined'
import { Alert, Button, Image, List, Space, Tag, Typography } from 'antd'
import type { Task, TaskLogEntry } from '@/types'
import CodeEditor from '@/components/CodeEditor'
import type { LocatorSnippet, UIElementNode } from './types'
import {
  formatDateTime,
  formatDuration,
  taskStatusColors,
  taskStatusText,
} from './scriptWorkspace'

const { Text } = Typography

interface ScriptWorkspacePanelProps {
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
  selectedUiElement: UIElementNode | null
  locatorSnippets: LocatorSnippet[]
  onAppendScriptSnippet: (snippet: LocatorSnippet) => void
}

export default function ScriptWorkspacePanel({
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
  selectedUiElement,
  locatorSnippets,
  onAppendScriptSnippet,
}: ScriptWorkspacePanelProps) {
  return (
    <div className="workspace-panel script-panel">
      <div className="workspace-toolbar">
        <Space direction="vertical" size={0}>
          <Text strong>编写自动化脚本</Text>
          <Text type="secondary">保存后留在当前投屏页</Text>
        </Space>
        <Space>
          <Button disabled={debugTaskActive} onClick={onOpenScriptPicker}>
            选择脚本
          </Button>
          <Button
            danger={debugTaskActive}
            icon={debugTaskActive ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
            loading={debugTaskActive ? debugCanceling : debugSubmitting}
            onClick={debugTaskActive ? onCancelDebugTask : onRunDebugScript}
          >
            {debugTaskActive ? '停止调试' : '运行调试'}
          </Button>
          <Button type="primary" onClick={onOpenSaveScriptModal}>
            保存
          </Button>
        </Space>
      </div>

      <div className="script-workspace-body">
        <div className="script-ide-shell">
          <div className="script-editor-wrap">
            <CodeEditor
              value={scriptContent}
              onChange={onScriptContentChange}
              height="100%"
              theme="vs-dark"
              highlightedLine={activeDebugLine}
              highlightedLineTone={failedDebugLine ? 'error' : 'current'}
            />
          </div>

          <div className="script-ide-status">
            <span>Python</span>
            <span>app.xxx SDK</span>
            <span>{scriptLineCount} 行</span>
            {failedDebugLine ? <span>失败停在第 {failedDebugLine} 行</span> : null}
            {!failedDebugLine && activeDebugLine ? <span>运行到第 {activeDebugLine} 行</span> : null}
          </div>
        </div>

        {debugTask && (
          <div className="script-debug-panel">
            <div className="script-debug-header">
              <Space size="small" wrap>
                <Text strong>运行日志</Text>
                <Tag color={taskStatusColors[debugTask.status]}>{taskStatusText[debugTask.status]}</Tag>
                {failedDebugLine ? <Tag color="error">失败行 {failedDebugLine}</Tag> : null}
                {!failedDebugLine && activeDebugLine ? <Tag color="processing">第 {activeDebugLine} 行</Tag> : null}
                <Text type="secondary" copyable={{ text: debugTask.id }}>
                  {debugTask.id}
                </Text>
              </Space>
              {debugTaskActive && (
                <Button danger size="small" icon={<DeleteOutlined />} loading={debugCanceling} onClick={onCancelDebugTask}>
                  取消任务
                </Button>
              )}
            </div>

            <div className="script-debug-summary">
              <span>设备：{debugTask.device_id || '-'}</span>
              <span>开始：{formatDateTime(debugTask.started_at || debugTask.created_at)}</span>
              <span>耗时：{formatDuration(debugTask)}</span>
            </div>

            {debugTask.error && (
              <Alert
                className="script-debug-alert"
                type="error"
                message={debugTask.error}
                showIcon
              />
            )}

            <List
              size="small"
              className="script-debug-log-list"
              dataSource={visibleDebugLogs}
              locale={{ emptyText: '暂无日志，任务启动后会自动刷新' }}
              renderItem={(item) => (
                <List.Item>
                  <Space size="small" align="start">
                    <Tag color={item.level === 'ERROR' ? 'error' : item.level === 'WARN' ? 'warning' : 'default'}>
                      {item.level}
                    </Tag>
                    <Text className="script-debug-log-message">{item.message}</Text>
                  </Space>
                </List.Item>
              )}
            />

            {debugScreenshots.length > 0 && (
              <Image.PreviewGroup>
                <div className="script-debug-screenshots">
                  {debugScreenshots.map((src, index) => (
                    <Image key={src} width={72} src={src} alt={`debug-screenshot-${index + 1}`} />
                  ))}
                </div>
              </Image.PreviewGroup>
            )}
          </div>
        )}

        <div className="script-assist-panel">
          <div className="script-assist-header">
            <Text strong>当前控件代码</Text>
            <Text type="secondary">选中控件后可插入定位片段</Text>
          </div>
          {selectedUiElement ? (
            <div className="script-snippet-list script-inline-snippets">
              {locatorSnippets.map((snippet) => (
                <div className="script-snippet-item" key={snippet.key}>
                  <div className="script-snippet-meta">
                    <Text strong>{snippet.title}</Text>
                    <Text type="secondary">{snippet.description}</Text>
                    <pre>{snippet.code}</pre>
                  </div>
                  <Button size="small" onClick={() => onAppendScriptSnippet(snippet)}>
                    插入
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <Text type="secondary">还没有选中控件。获取控件树并点击投屏上的控件后，这里会显示可插入的脚本片段。</Text>
          )}
        </div>
      </div>
    </div>
  )
}
