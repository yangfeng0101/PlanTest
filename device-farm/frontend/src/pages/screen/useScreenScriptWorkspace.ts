import { useCallback, useEffect, useMemo, useState } from 'react'
import { message } from 'antd'
import type { Device, Script, Task, TaskLogEntry } from '@/types'
import { scriptApi, taskApi } from '@/services/api'
import type { LocatorSnippet, UIElementNode } from './types'
import { releaseDebugSession } from './api'
import {
  buildDebugTags,
  countScriptLines,
  createDefaultScreenScript,
  findLatestScriptLine,
  isActiveTask,
  visibleDebugLogs as filterVisibleDebugLogs,
} from './scriptWorkspace'

interface UseScreenScriptWorkspaceOptions {
  selectedDevice: string
  currentDevice: Device | undefined
  selectedUiElement: UIElementNode | null
  uiElements: UIElementNode[]
  screenSessionActive: boolean
  onOpenScriptWorkspace: () => void
  onIosDebugSessionReleased: () => void
}

export default function useScreenScriptWorkspace({
  selectedDevice,
  currentDevice,
  selectedUiElement,
  uiElements,
  screenSessionActive,
  onOpenScriptWorkspace,
  onIosDebugSessionReleased,
}: UseScreenScriptWorkspaceOptions) {
  const [scriptSaving, setScriptSaving] = useState(false)
  const [scriptSaveModalOpen, setScriptSaveModalOpen] = useState(false)
  const [scriptPickerOpen, setScriptPickerOpen] = useState(false)
  const [scriptPickerLoading, setScriptPickerLoading] = useState(false)
  const [savedScripts, setSavedScripts] = useState<Script[]>([])
  const [scriptName, setScriptName] = useState('')
  const [scriptDescription, setScriptDescription] = useState('')
  const [scriptTags, setScriptTags] = useState<string[]>(['screen-debug'])
  const [scriptContent, setScriptContent] = useState('')
  const [loadedScript, setLoadedScript] = useState<Script | null>(null)
  const [debugScriptId, setDebugScriptId] = useState<string | null>(null)
  const [debugTask, setDebugTask] = useState<Task | null>(null)
  const [debugTaskLogs, setDebugTaskLogs] = useState<TaskLogEntry[]>([])
  const [debugSubmitting, setDebugSubmitting] = useState(false)
  const [debugCanceling, setDebugCanceling] = useState(false)
  const [debugCurrentLine, setDebugCurrentLine] = useState<number | null>(null)
  const [debugScriptSnapshot, setDebugScriptSnapshot] = useState('')

  const getCurrentPackageName = useCallback(() => (
    selectedUiElement?.package || uiElements.find((element) => element.package)?.package || 'com.example.app'
  ), [selectedUiElement, uiElements])

  const getDefaultScriptName = useCallback(
    () => `${currentDevice?.name || selectedDevice || '投屏'} 自动化脚本`,
    [currentDevice, selectedDevice],
  )

  const ensureScriptDraft = useCallback(() => {
    const packageName = getCurrentPackageName()
    if (!scriptContent.trim()) {
      setScriptContent(createDefaultScreenScript(packageName))
    }
  }, [getCurrentPackageName, scriptContent])

  const updateScriptContent = useCallback((value: string) => {
    setScriptContent(value)
  }, [])

  const openScriptPicker = useCallback(async () => {
    if (isActiveTask(debugTask)) {
      message.warning('调试任务正在运行，请先停止调试')
      return
    }

    setScriptPickerOpen(true)
    setScriptPickerLoading(true)
    try {
      const response = await scriptApi.getList()
      setSavedScripts(response.data.items || [])
    } catch (error) {
      console.error('Failed to fetch saved scripts:', error)
      message.error('获取已保存脚本失败')
    } finally {
      setScriptPickerLoading(false)
    }
  }, [debugTask])

  const closeScriptPicker = useCallback(() => {
    setScriptPickerOpen(false)
  }, [])

  const selectSavedScript = useCallback((script: Script) => {
    setScriptContent(script.content)
    setScriptName(script.name)
    setScriptDescription(script.description || '')
    setScriptTags(script.tags || [])
    setLoadedScript(script)
    setDebugCurrentLine(null)
    setDebugScriptSnapshot('')
    setScriptPickerOpen(false)
    onOpenScriptWorkspace()
    message.success('已载入脚本')
  }, [onOpenScriptWorkspace])

  const createExampleScript = useCallback(() => {
    setScriptContent(createDefaultScreenScript(getCurrentPackageName()))
    setScriptName('')
    setScriptDescription('')
    setScriptTags(['screen-debug'])
    setLoadedScript(null)
    setDebugCurrentLine(null)
    setDebugScriptSnapshot('')
    setDebugScriptId(null)
    setScriptPickerOpen(false)
    onOpenScriptWorkspace()
    message.success('已新建脚本')
  }, [getCurrentPackageName, onOpenScriptWorkspace])

  const activateScriptWriter = useCallback(() => {
    ensureScriptDraft()
    onOpenScriptWorkspace()
  }, [ensureScriptDraft, onOpenScriptWorkspace])

  const appendScriptSnippet = useCallback((snippet: LocatorSnippet) => {
    ensureScriptDraft()
    const packageName = getCurrentPackageName()
    setScriptContent((current) => {
      const base = (current.trim() ? current : createDefaultScreenScript(packageName)).trimEnd()
      return `${base}${base ? '\n\n' : ''}${snippet.code}\n`
    })
    onOpenScriptWorkspace()
    message.success('已插入脚本')
  }, [ensureScriptDraft, getCurrentPackageName, onOpenScriptWorkspace])

  const openSaveScriptModal = useCallback(() => {
    if (!scriptContent.trim()) {
      message.warning('请填写脚本内容')
      return
    }
    if (!scriptName.trim()) {
      setScriptName(getDefaultScriptName())
    }
    if (!scriptDescription.trim()) {
      setScriptDescription('从投屏页编写并保存的自动化脚本')
    }
    setScriptSaveModalOpen(true)
  }, [getDefaultScriptName, scriptContent, scriptDescription, scriptName])

  const closeSaveScriptModal = useCallback(() => {
    setScriptSaveModalOpen(false)
  }, [])

  const saveScript = useCallback(async () => {
    if (!scriptName.trim()) {
      message.warning('请填写脚本名称')
      return
    }
    if (!scriptContent.trim()) {
      message.warning('请填写脚本内容')
      return
    }

    setScriptSaving(true)
    try {
      const validation = await scriptApi.validate(scriptContent)
      if (!validation.data.valid) {
        message.error(validation.data.errors[0] || '脚本校验失败')
        return
      }
      if (validation.data.warnings.length > 0) {
        message.warning(validation.data.warnings[0])
      }

      const scriptData = {
        name: scriptName.trim(),
        description: scriptDescription.trim(),
        script_type: 'python',
        content: scriptContent,
        status: loadedScript?.status || 'draft',
        tags: scriptTags,
      } as const

      const response = loadedScript
        ? await scriptApi.update(loadedScript.id, scriptData)
        : await scriptApi.create(scriptData)

      setLoadedScript(response.data)
      message.success(loadedScript ? '脚本已更新' : '脚本已保存到脚本管理')
      setScriptSaveModalOpen(false)
    } catch (error) {
      console.error('Failed to save script from screen page:', error)
      message.error('保存脚本失败')
    } finally {
      setScriptSaving(false)
    }
  }, [loadedScript, scriptContent, scriptDescription, scriptName, scriptTags])

  const saveDebugDraft = useCallback(async (): Promise<Script> => {
    const debugTags = buildDebugTags(scriptTags)
    const data = {
      name: `${currentDevice?.name || selectedDevice || '投屏'} 调试脚本`,
      description: '投屏页自动保存的调试脚本草稿',
      script_type: 'python' as const,
      content: scriptContent,
      status: 'draft' as const,
      tags: debugTags,
    }

    if (debugScriptId) {
      try {
        const response = await scriptApi.update(debugScriptId, data)
        return response.data
      } catch (error) {
        console.warn('Failed to update debug draft, creating a new one:', error)
        setDebugScriptId(null)
      }
    }

    const response = await scriptApi.create(data)
    setDebugScriptId(response.data.id)
    return response.data
  }, [currentDevice, debugScriptId, scriptContent, scriptTags, selectedDevice])

  const runDebugScript = useCallback(async () => {
    if (isActiveTask(debugTask)) {
      message.warning('调试任务正在运行，请先停止调试')
      return
    }
    if (!scriptContent.trim()) {
      message.warning('请填写脚本内容')
      return
    }
    if (!selectedDevice) {
      message.warning('请先选择设备')
      return
    }
    if (!currentDevice || (currentDevice.status !== 'online' && !screenSessionActive)) {
      message.warning('当前设备不在线或已被占用，无法运行调试')
      return
    }

    setDebugSubmitting(true)
    try {
      const validation = await scriptApi.validate(scriptContent)
      if (!validation.data.valid) {
        message.error(validation.data.errors[0] || '脚本校验失败')
        return
      }
      if (validation.data.warnings.length > 0) {
        message.warning(validation.data.warnings[0])
      }

      const debugScript = await saveDebugDraft()
      const debugPlatform = currentDevice.os.toLowerCase() === 'ios' ? 'ios' : 'android'
      if (debugPlatform === 'ios') {
        const released = await releaseDebugSession(selectedDevice)
        if (!released) {
          throw new Error('释放 iOS 静态调试 session 失败，请稍后重试')
        }
        onIosDebugSessionReleased()
      }
      const response = await taskApi.create({
        script_id: debugScript.id,
        device_id: selectedDevice,
        device_platform: debugPlatform,
        device_capabilities: {
          automationName: debugPlatform === 'ios' ? 'XCUITest' : 'UiAutomator2',
          noReset: true,
        },
        parameters: {
          debug_trace_lines: true,
          screen_debug: screenSessionActive,
        },
      })

      setDebugTask(response.data)
      setDebugTaskLogs([])
      setDebugCurrentLine(null)
      setDebugScriptSnapshot(scriptContent)
      message.success('调试任务已创建')
    } catch (error) {
      console.error('Failed to run debug script:', error)
      const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
      message.error(detail || '调试任务创建失败，请确认设备在线且未被占用')
    } finally {
      setDebugSubmitting(false)
    }
  }, [currentDevice, debugTask, onIosDebugSessionReleased, saveDebugDraft, screenSessionActive, scriptContent, selectedDevice])

  const applyDebugLogs = useCallback((logs: TaskLogEntry[]) => {
    setDebugTaskLogs(logs)
    setDebugCurrentLine(findLatestScriptLine(logs))
  }, [])

  const cancelDebugTask = useCallback(async () => {
    if (!debugTask) return

    setDebugCanceling(true)
    try {
      await taskApi.cancel(debugTask.id)
      const [taskResponse, logsResponse] = await Promise.all([
        taskApi.getDetail(debugTask.id).catch(() => ({ data: { ...debugTask, status: 'cancelled' as const } })),
        taskApi.getLogs(debugTask.id, { limit: 1000 }),
      ])
      setDebugTask(taskResponse.data)
      applyDebugLogs(logsResponse.data)
      message.success('调试任务已取消')
    } catch (error) {
      console.error('Failed to cancel debug task:', error)
      message.error('调试任务取消失败')
    } finally {
      setDebugCanceling(false)
    }
  }, [applyDebugLogs, debugTask])

  const scriptLineCount = useMemo(() => countScriptLines(scriptContent), [scriptContent])
  const visibleDebugLogs = useMemo(
    () => filterVisibleDebugLogs(debugTaskLogs),
    [debugTaskLogs],
  )
  const debugScreenshots = debugTask?.result?.screenshots || []
  const debugTaskActive = isActiveTask(debugTask)
  const debugTaskId = debugTask?.id
  const debugTaskPollingActive = Boolean(debugTask && isActiveTask(debugTask))
  const activeDebugLine = debugScriptSnapshot === scriptContent ? debugCurrentLine : null
  const failedDebugLine = debugTask?.status === 'failed' ? activeDebugLine : null

  useEffect(() => {
    if (!debugTaskId || !debugTaskPollingActive) return

    let cancelled = false
    const pollTask = async () => {
      try {
        const [taskResponse, logsResponse] = await Promise.all([
          taskApi.getDetail(debugTaskId),
          taskApi.getLogs(debugTaskId, { limit: 1000 }),
        ])
        if (cancelled) return
        setDebugTask(taskResponse.data)
        applyDebugLogs(logsResponse.data)
      } catch (error) {
        console.error('Failed to poll debug task:', error)
      }
    }

    const timer = window.setInterval(pollTask, 2000)
    void pollTask()
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [applyDebugLogs, debugTaskId, debugTaskPollingActive])

  return {
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
  }
}
