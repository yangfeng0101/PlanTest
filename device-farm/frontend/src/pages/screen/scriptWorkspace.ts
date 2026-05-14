import type { Task, TaskLogEntry } from '@/types'

function pythonString(value: string) {
  return JSON.stringify(value)
}

export const taskStatusColors: Record<Task['status'], string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
  cancelled: 'warning',
}

export const taskStatusText: Record<Task['status'], string> = {
  pending: '排队中',
  running: '运行中',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
}

export function createDefaultScreenScript(packageName = 'com.example.app') {
  return `# 平台脚本示例：统一使用 app.xxx 调用平台能力
# 创建任务时只需要选择设备，启动哪个 App 由脚本自己控制
package = ${pythonString(packageName || 'com.example.app')}

app.log("script start")

# 启动或拉起 App
app.activate_app(package)
app.wait(5)

# 截图会自动上传到任务详情
app.screenshot()

# 常见弹窗处理
if app.has_text("同意"):
    app.click_text("同意", timeout=5)
    app.wait(2)
    app.screenshot()

if app.has_text("允许"):
    app.click_text("允许", timeout=5)
    app.wait(1)

# 页面断言
source = app.source()
assert_true(len(source) > 0, "页面源码为空，App 可能未正常启动")

# 退出 App，也可以使用 app.restart_app(package) 验证重启
app.terminate_app(package)

app.log("script passed")
test_pass()
`
}

export function isActiveTask(task?: Task | null) {
  return Boolean(task && ['pending', 'running'].includes(task.status))
}

export function formatDateTime(value?: string) {
  return value ? new Date(value).toLocaleString() : '-'
}

export function formatDuration(task?: Task | null) {
  if (!task) return '-'
  if (typeof task.result?.duration === 'number') {
    return `${task.result.duration.toFixed(2)}s`
  }
  if (task.started_at && task.finished_at) {
    const duration = (new Date(task.finished_at).getTime() - new Date(task.started_at).getTime()) / 1000
    return `${duration.toFixed(2)}s`
  }
  return '-'
}

export function countScriptLines(content: string) {
  return content.split(/\r\n|\r|\n/).length
}

export function findLatestScriptLine(logs: TaskLogEntry[]) {
  const latestLineEvent = [...logs]
    .reverse()
    .find((entry) => entry.event_type === 'script_line' && typeof entry.line_number === 'number')
  return latestLineEvent?.line_number || null
}

export function visibleDebugLogs(logs: TaskLogEntry[]) {
  return logs.filter((entry) => entry.event_type !== 'script_line')
}

export function buildDebugTags(tags: string[]) {
  return Array.from(new Set([...tags, 'screen-debug', 'debug-run']))
}
