import { useState, useEffect, useMemo, useRef } from 'react'
import { Alert, Card, Row, Col, Button, Table, Space, Modal, Form, Input, Select, Tag, message, Popconfirm, List, Typography, Image, Tooltip, Descriptions } from 'antd'
import PlusOutlined from '@ant-design/icons/PlusOutlined'
import EditOutlined from '@ant-design/icons/EditOutlined'
import DeleteOutlined from '@ant-design/icons/DeleteOutlined'
import PlayCircleOutlined from '@ant-design/icons/PlayCircleOutlined'
import CodeOutlined from '@ant-design/icons/CodeOutlined'
import HistoryOutlined from '@ant-design/icons/HistoryOutlined'
import CodeEditor from '@/components/CodeEditor'
import { useScriptStore } from '@/stores/scriptStore'
import { deviceApi, scriptApi, taskApi } from '@/services/api'
import type { Device, Script, Task, TaskLogEntry } from '@/types'

const { Option } = Select
const { TextArea } = Input
const { Text } = Typography

type RunFormValues = {
  device_id: string
}

const statusColors: Record<Task['status'], string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
  cancelled: 'warning',
}

const statusText: Record<Task['status'], string> = {
  pending: '排队中',
  running: '运行中',
  success: '成功',
  failed: '失败',
  cancelled: '已取消',
}

const defaultPythonScript = `# 平台脚本示例：统一使用 app.xxx 调用平台能力
# 创建任务时只需要选择设备，启动哪个 App 由脚本自己控制
package = "com.shizhuang.duapp"

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

const locatorTemplate = `package = "com.shizhuang.duapp"

app.log("locator case start")
app.activate_app(package)
app.wait(5)

# ID 定位，推荐优先使用稳定 resource-id
if app.exists(AppiumBy.ID, "com.shizhuang.duapp:id/search", timeout=3):
    app.click(AppiumBy.ID, "com.shizhuang.duapp:id/search", timeout=10)
else:
    app.log("未找到 ID，尝试文本定位", "WARN")
    app.click_text("搜索", timeout=5)

app.screenshot()
app.terminate_app(package)
test_pass()
`

const restartTemplate = `package = "com.shizhuang.duapp"

app.log("restart case start")
app.activate_app(package)
app.wait(3)
app.screenshot()

app.restart_app(package, wait_seconds=1)
app.wait(3)
app.screenshot()

app.terminate_app(package)
test_pass()
`

const textAssertTemplate = `package = "com.shizhuang.duapp"

app.log("text assert case start")
app.activate_app(package)
app.wait_text("首页", timeout=15)

assert_true(app.has_text("首页"), "没有进入首页")
app.screenshot()

app.terminate_app(package)
test_pass()
`

const loginTemplate = `package = "com.shizhuang.duapp"

app.log("login case start")
app.activate_app(package)
app.wait(5)

if app.has_text("登录"):
    app.click_text("登录", timeout=5)

# 示例：按实际 App 的 resource-id 修改
# username = app.find(AppiumBy.ID, "com.example:id/username", timeout=10)
# username.clear()
# username.send_keys("your_username")

app.screenshot()
app.terminate_app(package)
test_pass()
`

const scriptTemplates = [
  { key: 'smoke', label: 'App 冒烟测试', content: defaultPythonScript },
  { key: 'locator', label: 'XPath/ID 定位示例', content: locatorTemplate },
  { key: 'restart', label: 'App 启停重启', content: restartTemplate },
  { key: 'text', label: '文本断言', content: textAssertTemplate },
  { key: 'login', label: '登录流程模板', content: loginTemplate },
]

const formatDateTime = (value?: string) => value ? new Date(value).toLocaleString() : '-'

const formatDuration = (task?: Task | null) => {
  if (!task) return '-'
  if (typeof task.result?.duration === 'number') {
    return `${task.result.duration.toFixed(2)}s`
  }
  if (task.started_at && task.finished_at) {
    const duration = (new Date(task.finished_at).getTime() - new Date(task.started_at).getTime()) / 1000
    return `${Math.max(duration, 0).toFixed(2)}s`
  }
  return '-'
}

const isActiveTask = (task?: Task | null) => Boolean(task && ['pending', 'running'].includes(task.status))

export default function ScriptsPage() {
  const { scripts, loading, fetchScripts, createScript, updateScript, deleteScript } = useScriptStore()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingScript, setEditingScript] = useState<Script | null>(null)
  const [code, setCode] = useState('')
  const [form] = Form.useForm()
  const [runForm] = Form.useForm<RunFormValues>()
  const [keyword, setKeyword] = useState('')
  const [isRunModalOpen, setIsRunModalOpen] = useState(false)
  const [runningScript, setRunningScript] = useState<Script | null>(null)
  const [devices, setDevices] = useState<Device[]>([])
  const [devicesLoading, setDevicesLoading] = useState(false)
  const [taskSubmitting, setTaskSubmitting] = useState(false)
  const [currentTask, setCurrentTask] = useState<Task | null>(null)
  const [taskLogs, setTaskLogs] = useState<TaskLogEntry[]>([])
  const [activeTasks, setActiveTasks] = useState<Record<string, Task[]>>({})
  const [cancelingTasks, setCancelingTasks] = useState<Record<string, boolean>>({})
  const [isHistoryModalOpen, setIsHistoryModalOpen] = useState(false)
  const [historyScript, setHistoryScript] = useState<Script | null>(null)
  const [historyTasks, setHistoryTasks] = useState<Task[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [apiHelpOpen, setApiHelpOpen] = useState(false)
  const historyRequestRef = useRef(0)
  const scriptType = Form.useWatch('script_type', form) || 'python'
  const activeTaskIds = useMemo(
    () => Object.values(activeTasks)
      .flat()
      .filter(isActiveTask)
      .map((task) => task.id)
      .sort()
      .join(','),
    [activeTasks]
  )
  const visibleTaskLogs = useMemo(
    () => taskLogs.filter((entry) => entry.event_type !== 'script_line'),
    [taskLogs]
  )

  useEffect(() => {
    fetchScripts()
  }, [fetchScripts])

  useEffect(() => {
    const fetchActiveTasks = async () => {
      try {
        const [pendingResponse, runningResponse] = await Promise.all([
          taskApi.getList({ status: 'pending' }),
          taskApi.getList({ status: 'running' }),
        ])
        const tasks = [...pendingResponse.data.items, ...runningResponse.data.items]
        setActiveTasks(
          tasks.reduce<Record<string, Task[]>>((map, task) => {
            map[task.script_id] = [...(map[task.script_id] || []), task]
            return map
          }, {})
        )
      } catch (error) {
        console.error('Failed to fetch active tasks:', error)
      }
    }

    fetchActiveTasks()
  }, [])

  useEffect(() => {
    const taskIds = activeTaskIds ? activeTaskIds.split(',') : []
    if (taskIds.length === 0) {
      return
    }

    const timer = window.setInterval(async () => {
      try {
        const responses = await Promise.all(taskIds.map((taskId) => taskApi.getDetail(taskId)))
        const updatedTasks = responses.map((response) => response.data)

        setActiveTasks((previous) => {
          const next = { ...previous }
          updatedTasks.forEach((task) => {
            if (isActiveTask(task)) {
              const existingTasks = next[task.script_id] || []
              next[task.script_id] = existingTasks.some((item) => item.id === task.id)
                ? existingTasks.map((item) => item.id === task.id ? task : item)
                : [...existingTasks, task]
            } else {
              const remainingTasks = (next[task.script_id] || []).filter((item) => item.id !== task.id)
              if (remainingTasks.length > 0) {
                next[task.script_id] = remainingTasks
              } else {
                delete next[task.script_id]
              }
            }
          })
          return next
        })

        const selectedTask = updatedTasks.find((task) => task.id === currentTask?.id)
        if (selectedTask) {
          setCurrentTask(selectedTask)
          const logsResponse = await taskApi.getLogs(selectedTask.id)
          setTaskLogs(logsResponse.data)
        }
      } catch (error) {
        console.error('Failed to poll active tasks:', error)
      }
    }, 2000)

    return () => window.clearInterval(timer)
  }, [activeTaskIds, currentTask?.id])

  useEffect(() => {
    if (!currentTask || ['pending', 'running'].includes(currentTask.status)) {
      return
    }

    taskApi.getLogs(currentTask.id)
      .then((response) => setTaskLogs(response.data))
      .catch((error) => console.error('Failed to fetch final task logs:', error))
  }, [currentTask?.id, currentTask?.status])

  const handleCreate = () => {
    setEditingScript(null)
    setCode(defaultPythonScript)
    form.resetFields()
    form.setFieldsValue({ script_type: 'python', tags: [] })
    setIsModalOpen(true)
  }

  const handleApplyTemplate = (templateKey: string) => {
    const template = scriptTemplates.find((item) => item.key === templateKey)
    if (template) {
      setCode(template.content)
      message.success(`已应用模板：${template.label}`)
    }
  }

  const handleEdit = (script: Script) => {
    setEditingScript(script)
    setCode(script.content)
    form.setFieldsValue(script)
    setIsModalOpen(true)
  }

  const handleDelete = async (id: string) => {
    await deleteScript(id)
    message.success('脚本删除成功')
  }

  const validateScriptContent = async (content: string) => {
    const response = await scriptApi.validate(content)
    const { errors, warnings } = response.data
    if (errors.length > 0) {
      Modal.error({
        title: '脚本校验失败',
        content: (
          <List
            size="small"
            dataSource={errors}
            renderItem={(item) => <List.Item>{item}</List.Item>}
          />
        ),
      })
      return false
    }
    if (warnings.length > 0) {
      message.warning(warnings[0])
    }
    return true
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const valid = await validateScriptContent(code)
      if (!valid) return

      const scriptData = {
        ...values,
        content: code,
      }

      if (editingScript) {
        await updateScript(editingScript.id, scriptData)
        message.success('脚本更新成功')
      } else {
        await createScript(scriptData)
        message.success('脚本创建成功')
      }
      setIsModalOpen(false)
    } catch (error) {
      console.error('Validation failed:', error)
    }
  }

  const fetchDevices = async () => {
    setDevicesLoading(true)
    try {
      const response = await deviceApi.getList()
      setDevices(response.data.devices || [])
    } catch (error) {
      console.error('Failed to fetch devices:', error)
      message.error('设备列表获取失败')
    } finally {
      setDevicesLoading(false)
    }
  }

  const handleRun = async (script: Script) => {
    setRunningScript(script)
    setCurrentTask(null)
    setTaskLogs([])
    runForm.resetFields()
    setIsRunModalOpen(true)
    await fetchDevices()
  }

  const handleCreateTask = async () => {
    if (!runningScript) return

    try {
      const valid = await validateScriptContent(runningScript.content)
      if (!valid) return

      const values = await runForm.validateFields()
      const deviceCapabilities: Record<string, unknown> = {
        automationName: 'UiAutomator2',
        noReset: true,
      }

      setTaskSubmitting(true)
      const response = await taskApi.create({
        script_id: runningScript.id,
        device_id: values.device_id,
        device_platform: 'android',
        device_capabilities: deviceCapabilities,
        parameters: {},
      })
      setActiveTasks((previous) => ({
        ...previous,
        [runningScript.id]: [...(previous[runningScript.id] || []), response.data],
      }))
      setCurrentTask(null)
      setTaskLogs([])
      setIsRunModalOpen(false)
      setRunningScript(null)
      message.success('任务已创建')
    } catch (error) {
      console.error('Failed to create task:', error)
      message.error('任务创建失败，请确认设备在线且未被占用')
    } finally {
      setTaskSubmitting(false)
    }
  }

  const handleViewTask = async (script: Script, task: Task) => {
    setRunningScript(script)
    setCurrentTask(task)
    setIsHistoryModalOpen(false)
    setIsRunModalOpen(true)
    if (isActiveTask(task)) {
      setActiveTasks((previous) => {
        const existingTasks = previous[task.script_id] || []
        return {
          ...previous,
          [task.script_id]: existingTasks.some((item) => item.id === task.id)
            ? existingTasks.map((item) => item.id === task.id ? task : item)
            : [...existingTasks, task],
        }
      })
    }
    try {
      const logsResponse = await taskApi.getLogs(task.id)
      setTaskLogs(logsResponse.data)
    } catch (error) {
      console.error('Failed to fetch task logs:', error)
    }
  }

  const handleViewHistory = async (script: Script) => {
    const requestId = historyRequestRef.current + 1
    historyRequestRef.current = requestId
    setHistoryScript(script)
    setHistoryTasks([])
    setIsHistoryModalOpen(true)
    setHistoryLoading(true)
    try {
      const response = await taskApi.getList({ script_id: script.id, page: 1, page_size: 50 })
      if (historyRequestRef.current !== requestId) return
      setHistoryTasks(response.data.items)
    } catch (error) {
      if (historyRequestRef.current !== requestId) return
      console.error('Failed to fetch task history:', error)
      message.error('运行记录获取失败')
    } finally {
      if (historyRequestRef.current === requestId) {
        setHistoryLoading(false)
      }
    }
  }

  const handleCancelTask = async (task: Task) => {
    setCancelingTasks((previous) => ({ ...previous, [task.id]: true }))
    try {
      await taskApi.cancel(task.id)
      setActiveTasks((previous) => {
        const next = { ...previous }
        const remainingTasks = (next[task.script_id] || []).filter((item) => item.id !== task.id)
        if (remainingTasks.length > 0) {
          next[task.script_id] = remainingTasks
        } else {
          delete next[task.script_id]
        }
        return next
      })
      if (currentTask?.id === task.id) {
        setCurrentTask({ ...task, status: 'cancelled' })
        const logsResponse = await taskApi.getLogs(task.id)
        setTaskLogs(logsResponse.data)
      }
      message.success('任务已取消')
    } catch (error) {
      console.error('Failed to cancel task:', error)
      message.error('任务取消失败')
    } finally {
      setCancelingTasks((previous) => {
        const next = { ...previous }
        delete next[task.id]
        return next
      })
    }
  }

  const languageColors: Record<string, string> = {
    python: 'blue',
  }

  const renderTaskFooter = () => {
    if (!currentTask) return undefined

    return (
      <Space>
        {isActiveTask(currentTask) && (
          <Button
            danger
            icon={<DeleteOutlined />}
            loading={cancelingTasks[currentTask.id]}
            onClick={() => handleCancelTask(currentTask)}
          >
            取消任务
          </Button>
        )}
        <Button onClick={() => setIsRunModalOpen(false)}>关闭</Button>
      </Space>
    )
  }

  const renderActions = (record: Script) => {
    const scriptActiveTasks = activeTasks[record.id] || []
    const activeTask = scriptActiveTasks.find(isActiveTask)
    const active = Boolean(activeTask)

    return (
      <Space size={4} style={{ whiteSpace: 'nowrap' }}>
        {activeTask ? (
          <>
            <Tooltip title={`查看任务：${statusText[activeTask.status]}${scriptActiveTasks.length > 1 ? `（共 ${scriptActiveTasks.length} 个）` : ''}`}>
              <Button
                type="text"
                size="small"
                icon={<PlayCircleOutlined spin />}
                onClick={() => handleViewTask(record, activeTask)}
              />
            </Tooltip>
            <Tooltip title="取消任务">
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                loading={cancelingTasks[activeTask.id]}
                onClick={() => handleCancelTask(activeTask)}
              />
            </Tooltip>
          </>
        ) : (
          <Tooltip title="运行">
            <Button type="text" size="small" icon={<PlayCircleOutlined />} onClick={() => handleRun(record)} />
          </Tooltip>
        )}
        <Tooltip title="运行记录">
          <Button type="text" size="small" icon={<HistoryOutlined />} onClick={() => handleViewHistory(record)} />
        </Tooltip>
        <Tooltip title="编辑">
          <Button type="text" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
        </Tooltip>
        <Popconfirm
          title="确定要删除这个脚本吗?"
          onConfirm={() => handleDelete(record.id)}
          okText="确定"
          cancelText="取消"
          disabled={active}
        >
          <Tooltip title={active ? '任务执行中，暂不能删除' : '删除'}>
            <Button type="text" size="small" danger disabled={active} icon={<DeleteOutlined />} />
          </Tooltip>
        </Popconfirm>
      </Space>
    )
  }

  const columns = [
    {
      title: '脚本名称',
      dataIndex: 'name',
      key: 'name',
      width: 260,
      ellipsis: true,
      render: (name: string, record: Script) => (
        <a onClick={() => handleEdit(record)}>
          <CodeOutlined style={{ marginRight: 8 }} />
          {name}
        </a>
      ),
    },
    {
      title: '语言',
      dataIndex: 'script_type',
      key: 'script_type',
      width: 120,
      render: (scriptType: string) => (
        <Tag color={languageColors[scriptType] || 'default'}>{scriptType.toUpperCase()}</Tag>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      width: 260,
      ellipsis: true,
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 180,
      render: (tags: string[]) => (
        <>
          {tags.map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          ))}
        </>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (value: string) => value ? new Date(value).toLocaleString() : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 190,
      align: 'center' as const,
      render: (_: unknown, record: Script) => renderActions(record),
    },
  ]

  const historyColumns = [
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: Task['status']) => (
        <Tag color={statusColors[status]}>{statusText[status]}</Tag>
      ),
    },
    {
      title: '设备',
      dataIndex: 'device_id',
      key: 'device_id',
      width: 170,
      ellipsis: true,
      render: (value?: string) => value || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '耗时',
      key: 'duration',
      width: 90,
      render: (_: unknown, task: Task) => formatDuration(task),
    },
    {
      title: '任务 ID',
      dataIndex: 'id',
      key: 'id',
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      align: 'center' as const,
      render: (_: unknown, task: Task) => (
        <Button
          type="link"
          size="small"
          onClick={() => historyScript && handleViewTask(historyScript, task)}
        >
          详情
        </Button>
      ),
    },
  ]

  const filteredScripts = scripts.filter((script) =>
    script.name.toLowerCase().includes(keyword.toLowerCase()) ||
    (script.description || '').toLowerCase().includes(keyword.toLowerCase())
  )

  const androidCompatibleDevices = new Set(['android', 'harmony', 'harmonyos'])
  const onlineDevices = devices.filter(
    (device) => device.status === 'online' && androidCompatibleDevices.has(device.os?.toLowerCase() || '')
  )
  const screenshots = currentTask?.result?.screenshots || []

  return (
    <div>
      <Card
        title="脚本管理"
        extra={
          <Space>
            <Input.Search
              placeholder="搜索脚本"
              allowClear
              style={{ width: 250 }}
              onSearch={setKeyword}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              新建脚本
            </Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={filteredScripts}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          tableLayout="fixed"
        />
      </Card>

      <Modal
        title={editingScript ? '编辑脚本' : '新建脚本'}
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        onOk={handleSave}
        width={900}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="name"
                label="脚本名称"
                rules={[{ required: true, message: '请输入脚本名称' }]}
              >
                <Input placeholder="请输入脚本名称" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="script_type"
                label="语言类型"
                rules={[{ required: true, message: '请选择语言类型' }]}
              >
                <Select placeholder="请选择语言类型">
                  <Option value="python">Python</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="请输入脚本描述" />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入标签后按回车添加" />
          </Form.Item>
          <Form.Item
            label={
              <Space>
                <span>脚本内容</span>
                <Select
                  size="small"
                  placeholder="选择模板"
                  style={{ width: 160 }}
                  onChange={handleApplyTemplate}
                  value={undefined}
                >
                  {scriptTemplates.map((template) => (
                    <Option key={template.key} value={template.key}>
                      {template.label}
                    </Option>
                  ))}
                </Select>
                <Button size="small" type="link" onClick={() => setApiHelpOpen(true)}>
                  脚本 API
                </Button>
              </Space>
            }
          >
            <div style={{ border: '1px solid #d9d9d9', borderRadius: 4, overflow: 'hidden' }}>
              <CodeEditor
                value={code}
                language={scriptType}
                onChange={setCode}
              />
            </div>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="脚本 API 速查"
        open={apiHelpOpen}
        onCancel={() => setApiHelpOpen(false)}
        footer={<Button onClick={() => setApiHelpOpen(false)}>关闭</Button>}
        width={760}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="推荐统一使用 app.xxx。创建任务只选择设备，启动哪个 App 由脚本控制。"
          />
          <Descriptions size="small" bordered column={1}>
            <Descriptions.Item label="App 控制">app.activate_app / app.terminate_app / app.restart_app</Descriptions.Item>
            <Descriptions.Item label="基础能力">app.log / app.wait / app.screenshot / app.source</Descriptions.Item>
            <Descriptions.Item label="手势输入">app.tap / app.swipe / app.input_text / app.clear_text / app.press_key / app.back / app.home</Descriptions.Item>
            <Descriptions.Item label="元素定位">app.find / app.find_all / app.exists / app.wait_element / app.click / app.get_text</Descriptions.Item>
            <Descriptions.Item label="文本">app.has_text / app.assert_text / app.wait_text / app.click_text</Descriptions.Item>
            <Descriptions.Item label="结果">test_pass / test_fail / test_skip / assert_true / assert_equal</Descriptions.Item>
          </Descriptions>
          <Text code>
            app.click(AppiumBy.ID, "com.example:id/button", timeout=10)
          </Text>
          <Text code>
            app.click(AppiumBy.XPATH, '//*[@text="登录"]', timeout=10)
          </Text>
        </Space>
      </Modal>

      <Modal
        title={historyScript ? `运行记录：${historyScript.name}` : '运行记录'}
        open={isHistoryModalOpen}
        onCancel={() => setIsHistoryModalOpen(false)}
        footer={<Button onClick={() => setIsHistoryModalOpen(false)}>关闭</Button>}
        width={920}
      >
        <Table
          size="small"
          columns={historyColumns}
          dataSource={historyTasks}
          rowKey="id"
          loading={historyLoading}
          pagination={{ pageSize: 10 }}
          tableLayout="fixed"
          locale={{ emptyText: '暂无运行记录' }}
        />
      </Modal>

      <Modal
        title={currentTask ? `任务详情：${runningScript?.name || currentTask.script_id}` : runningScript ? `运行脚本：${runningScript.name}` : '运行脚本'}
        open={isRunModalOpen}
        onCancel={() => setIsRunModalOpen(false)}
        onOk={currentTask ? undefined : handleCreateTask}
        okText="创建任务"
        cancelText="关闭"
        confirmLoading={taskSubmitting}
        width={760}
        footer={renderTaskFooter()}
      >
        {!currentTask && (
          <Form form={runForm} layout="vertical">
            <Form.Item
              name="device_id"
              label="设备"
              rules={[{ required: true, message: '请选择设备' }]}
            >
              <Select
                loading={devicesLoading}
                placeholder="请选择在线 Android/HarmonyOS 设备"
                notFoundContent={devicesLoading ? '加载中' : '暂无在线 Android/HarmonyOS 设备'}
              >
                {onlineDevices.map((device) => (
                  <Option key={device.id} value={device.id}>
                    {device.name || device.id} ({device.id})
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Form>
        )}

        {currentTask && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions size="small" bordered column={2}>
              <Descriptions.Item label="脚本">{runningScript?.name || currentTask.script_id}</Descriptions.Item>
              <Descriptions.Item label="设备">{currentTask.device_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="任务 ID">{currentTask.id}</Descriptions.Item>
              <Descriptions.Item label="平台">{currentTask.device_platform}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(currentTask.created_at)}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatDateTime(currentTask.started_at)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatDateTime(currentTask.finished_at)}</Descriptions.Item>
              <Descriptions.Item label="运行耗时">{formatDuration(currentTask)}</Descriptions.Item>
              <Descriptions.Item label="截图数量">{screenshots.length}</Descriptions.Item>
              <Descriptions.Item label="错误数量">{currentTask.result?.errors?.length || 0}</Descriptions.Item>
            </Descriptions>
            <Alert
              type={currentTask.status === 'failed' ? 'error' : currentTask.status === 'success' ? 'success' : 'info'}
              message={
                <Space>
                  <span>任务状态</span>
                  <Tag color={statusColors[currentTask.status]}>{statusText[currentTask.status]}</Tag>
                  <Text type="secondary">{currentTask.id}</Text>
                </Space>
              }
              description={currentTask.error || undefined}
              showIcon
            />
            <List
              size="small"
              header="执行日志"
              bordered
              dataSource={visibleTaskLogs}
              locale={{ emptyText: '暂无日志' }}
              renderItem={(item) => (
                <List.Item>
                  <Space>
                    <Tag color={item.level === 'ERROR' ? 'error' : item.level === 'WARN' ? 'warning' : 'default'}>
                      {item.level}
                    </Tag>
                    <Text>{item.message}</Text>
                  </Space>
                </List.Item>
              )}
            />
            {screenshots.length > 0 && (
              <Image.PreviewGroup>
                <Space wrap>
                  {screenshots.map((src, index) => (
                    <Image key={src} width={120} src={src} alt={`screenshot-${index + 1}`} />
                  ))}
                </Space>
              </Image.PreviewGroup>
            )}
          </Space>
        )}
      </Modal>
    </div>
  )
}
