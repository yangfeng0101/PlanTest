import { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Progress,
  Modal,
  Descriptions,
  Tabs,
  Statistic,
  Row,
  Col,
  Badge,
  Alert,
  Spin,
  message,
} from 'antd'
import ReloadOutlined from '@ant-design/icons/ReloadOutlined'
import EyeOutlined from '@ant-design/icons/EyeOutlined'
import DownloadOutlined from '@ant-design/icons/DownloadOutlined'
import MobileOutlined from '@ant-design/icons/MobileOutlined'
import type { ColumnsType } from 'antd/es/table'

interface SubTask {
  task_id: string
  device_id: string
  status: string
  started_at?: string
  finished_at?: string
  result?: {
    total_tests?: number
    passed_tests?: number
    failed_tests?: number
  }
  error?: string
}

interface ParallelTask {
  id: string
  script_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'partial'
  total_devices: number
  completed_devices: number
  failed_devices: number
  sub_tasks: SubTask[]
  created_at: string
  started_at?: string
  finished_at?: string
}

interface ParallelTaskSummary {
  parallel_task_id: string
  script_id: string
  status: string
  total_devices: number
  completed_devices: number
  failed_devices: number
  success_rate: number
  total_tests: number
  passed_tests: number
  failed_tests: number
  total_duration: number
  sub_tasks: SubTask[]
}

export default function ParallelExecutionPage() {
  const [tasks, setTasks] = useState<ParallelTask[]>([])
  const [loading, setLoading] = useState(false)
  const [detailVisible, setDetailVisible] = useState(false)
  const [currentTask, setCurrentTask] = useState<ParallelTask | null>(null)
  const [currentSummary, setCurrentSummary] = useState<ParallelTaskSummary | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [pollingTaskId, setPollingTaskId] = useState<string | null>(null)

  const fetchTasks = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/v1/tasks/parallel')
      const data = await response.json()
      setTasks(data || [])
    } catch (error) {
      console.error('Failed to fetch parallel tasks:', error)
      // Mock data for development
      setTasks([
        {
          id: 'pt-001',
          script_id: 'script-login',
          status: 'completed',
          total_devices: 5,
          completed_devices: 5,
          failed_devices: 0,
          sub_tasks: [],
          created_at: '2024-01-15 10:00:00',
          started_at: '2024-01-15 10:00:05',
          finished_at: '2024-01-15 10:05:30',
        },
        {
          id: 'pt-002',
          script_id: 'script-payment',
          status: 'partial',
          total_devices: 4,
          completed_devices: 3,
          failed_devices: 1,
          sub_tasks: [],
          created_at: '2024-01-15 11:00:00',
          started_at: '2024-01-15 11:00:05',
          finished_at: '2024-01-15 11:03:20',
        },
      ])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchTasks()
  }, [fetchTasks])

  // Polling for running tasks
  useEffect(() => {
    if (!pollingTaskId) return

    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/v1/tasks/parallel/${pollingTaskId}`)
        const task = await response.json()

        if (task.status === 'completed' || task.status === 'failed' || task.status === 'partial') {
          setPollingTaskId(null)
          fetchTasks()
        } else {
          // Update the task in the list
          setTasks(prev => prev.map(t => t.id === pollingTaskId ? task : t))
        }
      } catch (error) {
        console.error('Failed to poll task status:', error)
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [pollingTaskId, fetchTasks])

  const handleViewDetail = async (task: ParallelTask) => {
    setCurrentTask(task)
    setDetailVisible(true)
    setSummaryLoading(true)

    try {
      const response = await fetch(`/api/v1/tasks/parallel/${task.id}/summary`)
      const summary = await response.json()
      setCurrentSummary(summary)
    } catch (error) {
      console.error('Failed to fetch summary:', error)
    } finally {
      setSummaryLoading(false)
    }
  }

  const handleDownloadReport = async (taskId: string) => {
    try {
      // Trigger report generation
      const response = await fetch(`/api/v1/reports/parallel/${taskId}/download?format=html`)
      if (response.ok) {
        const blob = await response.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `parallel_report_${taskId}.html`
        a.click()
        URL.revokeObjectURL(url)
        message.success('Report downloaded successfully')
      } else {
        message.error('Failed to download report')
      }
    } catch (error) {
      console.error('Failed to download report:', error)
      message.error('Failed to download report')
    }
  }

  const getStatusTag = (status: string) => {
    const statusConfig: Record<string, { color: string; text: string }> = {
      pending: { color: 'default', text: 'Pending' },
      running: { color: 'processing', text: 'Running' },
      completed: { color: 'success', text: 'Success' },
      failed: { color: 'error', text: 'Failed' },
      partial: { color: 'warning', text: 'Partial' },
    }
    const config = statusConfig[status] || { color: 'default', text: status }
    return <Tag color={config.color}>{config.text}</Tag>
  }

  const getProgressPercent = (task: ParallelTask) => {
    if (task.total_devices === 0) return 0
    return Math.round(((task.completed_devices + task.failed_devices) / task.total_devices) * 100)
  }

  const columns: ColumnsType<ParallelTask> = [
    {
      title: 'Task ID',
      dataIndex: 'id',
      key: 'id',
      width: 150,
    },
    {
      title: 'Script ID',
      dataIndex: 'script_id',
      key: 'script_id',
      width: 150,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => getStatusTag(status),
    },
    {
      title: 'Progress',
      key: 'progress',
      width: 200,
      render: (_: unknown, record: ParallelTask) => (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Progress
            percent={getProgressPercent(record)}
            status={record.status === 'failed' ? 'exception' : record.status === 'running' ? 'active' : 'success'}
            size="small"
          />
          <Space size="small">
            <Badge status="success" text={`${record.completed_devices} passed`} />
            <Badge status="error" text={`${record.failed_devices} failed`} />
          </Space>
        </Space>
      ),
    },
    {
      title: 'Devices',
      key: 'devices',
      width: 100,
      render: (_: unknown, record: ParallelTask) => (
        <Space>
          <MobileOutlined />
          <span>{record.total_devices}</span>
        </Space>
      ),
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 150,
      render: (_: unknown, record: ParallelTask) => (
        <Space>
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => handleViewDetail(record)}
          >
            Detail
          </Button>
          {(record.status === 'completed' || record.status === 'partial') && (
            <Button
              type="link"
              icon={<DownloadOutlined />}
              onClick={() => handleDownloadReport(record.id)}
            >
              Report
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Card
        title="Parallel Execution"
        extra={
          <Button icon={<ReloadOutlined />} onClick={fetchTasks}>
            Refresh
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={tasks}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal
        title="Parallel Execution Detail"
        open={detailVisible}
        onCancel={() => {
          setDetailVisible(false)
          setCurrentSummary(null)
        }}
        footer={null}
        width={900}
      >
        {currentTask && (
          <div>
            <Descriptions bordered column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="Task ID">{currentTask.id}</Descriptions.Item>
              <Descriptions.Item label="Script ID">{currentTask.script_id}</Descriptions.Item>
              <Descriptions.Item label="Status">
                {getStatusTag(currentTask.status)}
              </Descriptions.Item>
              <Descriptions.Item label="Total Devices">
                {currentTask.total_devices}
              </Descriptions.Item>
              <Descriptions.Item label="Created">
                {currentTask.created_at}
              </Descriptions.Item>
              <Descriptions.Item label="Duration">
                {currentTask.started_at && currentTask.finished_at
                  ? `${((new Date(currentTask.finished_at).getTime() - new Date(currentTask.started_at).getTime()) / 1000).toFixed(2)}s`
                  : '-'}
              </Descriptions.Item>
            </Descriptions>

            {currentTask.status === 'running' && (
              <Alert
                message="Task is running..."
                description="Progress will update automatically"
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
              />
            )}

            {summaryLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <Spin />
              </div>
            ) : currentSummary ? (
              <>
                <Card title="Summary" style={{ marginBottom: 16 }}>
                  <Row gutter={16}>
                    <Col span={6}>
                      <Statistic
                        title="Total Devices"
                        value={currentSummary.total_devices}
                        prefix={<MobileOutlined />}
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="Success Rate"
                        value={currentSummary.success_rate}
                        suffix="%"
                        valueStyle={{ color: currentSummary.success_rate === 100 ? '#52c41a' : '#faad14' }}
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="Total Tests"
                        value={currentSummary.total_tests}
                      />
                    </Col>
                    <Col span={6}>
                      <Statistic
                        title="Test Pass Rate"
                        value={currentSummary.total_tests > 0 ? ((currentSummary.passed_tests / currentSummary.total_tests) * 100).toFixed(1) : 0}
                        suffix="%"
                      />
                    </Col>
                  </Row>
                </Card>

                <Tabs
                  items={[
                    {
                      key: 'devices',
                      label: 'Device Results',
                      children: (
                        <Table
                          dataSource={currentSummary.sub_tasks}
                          rowKey="task_id"
                          size="small"
                          columns={[
                            {
                              title: 'Device ID',
                              dataIndex: 'device_id',
                              key: 'device_id',
                            },
                            {
                              title: 'Status',
                              dataIndex: 'status',
                              key: 'status',
                              render: (status: string) => (
                                <Tag color={status === 'success' ? 'green' : 'red'}>
                                  {status}
                                </Tag>
                              ),
                            },
                            {
                              title: 'Tests',
                              key: 'tests',
                              render: (_: unknown, record: SubTask) => (
                                <Space>
                                  <Badge color="green" text={record.result?.passed_tests || 0} />
                                  <Badge color="red" text={record.result?.failed_tests || 0} />
                                </Space>
                              ),
                            },
                            {
                              title: 'Error',
                              dataIndex: 'error',
                              key: 'error',
                              ellipsis: true,
                            },
                          ]}
                        />
                      ),
                    },
                    {
                      key: 'failed',
                      label: `Failed Devices (${currentSummary.failed_devices})`,
                      children: (
                        <Table
                          dataSource={currentSummary.sub_tasks.filter(s => s.status !== 'success')}
                          rowKey="task_id"
                          size="small"
                          columns={[
                            {
                              title: 'Device ID',
                              dataIndex: 'device_id',
                              key: 'device_id',
                            },
                            {
                              title: 'Status',
                              dataIndex: 'status',
                              key: 'status',
                              render: (status: string) => (
                                <Tag color="red">{status}</Tag>
                              ),
                            },
                            {
                              title: 'Error',
                              dataIndex: 'error',
                              key: 'error',
                            },
                          ]}
                        />
                      ),
                    },
                  ]}
                />
              </>
            ) : (
              <Alert
                message="Summary not available"
                description="The task may still be running or aggregation has not been performed."
                type="warning"
                showIcon
              />
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
