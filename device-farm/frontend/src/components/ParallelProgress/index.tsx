import { useEffect, useState } from 'react'
import { Card, Progress, Tag, Space, Table, Badge, Spin, Alert, Row, Col, Statistic, Button, Modal, Descriptions, Empty } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
  SyncOutlined,
  EyeOutlined,
} from '@ant-design/icons'
import type { ParallelTask, SubTask } from '@/types'

interface ParallelProgressProps {
  parallelTaskId: string
  onComplete?: (task: ParallelTask) => void
  pollInterval?: number
}

const statusConfig: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
  pending: { color: 'default', text: '等待中', icon: <ClockCircleOutlined /> },
  running: { color: 'processing', text: '执行中', icon: <SyncOutlined spin /> },
  success: { color: 'success', text: '成功', icon: <CheckCircleOutlined /> },
  failed: { color: 'error', text: '失败', icon: <CloseCircleOutlined /> },
  timeout: { color: 'warning', text: '超时', icon: <CloseCircleOutlined /> },
  cancelled: { color: 'default', text: '已取消', icon: <CloseCircleOutlined /> },
}

const taskStatusConfig: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '等待中' },
  running: { color: 'processing', text: '执行中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
  partial: { color: 'warning', text: '部分成功' },
}

export default function ParallelProgress({
  parallelTaskId,
  onComplete,
  pollInterval = 2000,
}: ParallelProgressProps) {
  const [task, setTask] = useState<ParallelTask | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [logVisible, setLogVisible] = useState(false)
  const [selectedDevice, setSelectedDevice] = useState<SubTask | null>(null)
  const [deviceLogs, setDeviceLogs] = useState<string[]>([])

  useEffect(() => {
    let mounted = true
    let intervalId: ReturnType<typeof setInterval> | null = null

    const fetchTask = async () => {
      try {
        const response = await fetch(`/api/v1/tasks/parallel/${parallelTaskId}`)
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        const data = await response.json()
        if (mounted) {
          setTask(data)
          setError(null)

          // Stop polling if task is complete
          if (['completed', 'failed', 'partial'].includes(data.status)) {
            if (intervalId) {
              clearInterval(intervalId)
            }
            onComplete?.(data)
          }
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Unknown error')
        }
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }

    fetchTask()

    // Start polling
    intervalId = setInterval(fetchTask, pollInterval)

    return () => {
      mounted = false
      if (intervalId) {
        clearInterval(intervalId)
      }
    }
  }, [parallelTaskId, pollInterval, onComplete])

  const handleViewLogs = async (subTask: SubTask) => {
    setSelectedDevice(subTask)
    setLogVisible(true)
    try {
      const response = await fetch(
        `/api/v1/tasks/parallel/${parallelTaskId}/devices/${subTask.device_id}/logs`
      )
      if (response.ok) {
        const logs = await response.json()
        setDeviceLogs(logs)
      } else {
        setDeviceLogs(['Failed to fetch logs'])
      }
    } catch {
      setDeviceLogs(['Error fetching logs'])
    }
  }

  if (loading) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin indicator={<LoadingOutlined style={{ fontSize: 24 }} spin />} />
          <p style={{ marginTop: 16, color: '#666' }}>Loading parallel task...</p>
        </div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <Alert type="error" message="Error" description={error} />
      </Card>
    )
  }

  if (!task) {
    return (
      <Card>
        <Empty description="No task found" />
      </Card>
    )
  }

  const progressPercent = task.total_devices > 0
    ? Math.round(((task.completed_devices + task.failed_devices) / task.total_devices) * 100)
    : 0

  const columns = [
    {
      title: '设备ID',
      dataIndex: 'device_id',
      key: 'device_id',
      width: 150,
    },
    {
      title: '任务ID',
      dataIndex: 'task_id',
      key: 'task_id',
      width: 150,
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const config = statusConfig[status] || { color: 'default', text: status }
        return <Tag color={config.color} icon={config.icon}>{config.text}</Tag>
      },
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 180,
      render: (time: string) => time ? new Date(time).toLocaleString() : '-',
    },
    {
      title: '完成时间',
      dataIndex: 'finished_at',
      key: 'finished_at',
      width: 180,
      render: (time: string) => time ? new Date(time).toLocaleString() : '-',
    },
    {
      title: '错误信息',
      dataIndex: 'error',
      key: 'error',
      ellipsis: true,
      render: (error: string) => error ? (
        <Tag color="error">{error}</Tag>
      ) : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: unknown, record: SubTask) => (
        <Button
          type="link"
          icon={<EyeOutlined />}
          onClick={() => handleViewLogs(record)}
          disabled={record.status === 'pending'}
        >
          日志
        </Button>
      ),
    },
  ]

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={24}>
          <Col span={6}>
            <Statistic
              title="总体进度"
              value={task.completed_devices + task.failed_devices}
              suffix={`/ ${task.total_devices}`}
            />
            <Progress
              percent={progressPercent}
              status={task.status === 'running' ? 'active' : undefined}
              style={{ marginTop: 8 }}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="成功设备"
              value={task.completed_devices}
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="失败设备"
              value={task.failed_devices}
              valueStyle={{ color: task.failed_devices > 0 ? '#ff4d4f' : undefined }}
              prefix={<CloseCircleOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="任务状态"
              value={taskStatusConfig[task.status]?.text || task.status}
              valueStyle={{
                color: taskStatusConfig[task.status]?.color === 'success' ? '#52c41a' :
                       taskStatusConfig[task.status]?.color === 'error' ? '#ff4d4f' :
                       taskStatusConfig[task.status]?.color === 'warning' ? '#faad14' : undefined
              }}
            />
          </Col>
        </Row>
      </Card>

      <Card
        title={
          <Space>
            <span>设备执行详情</span>
            <Badge count={task.sub_tasks.filter(s => s.status === 'running').length} showZero color="#1890ff" />
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={task.sub_tasks}
          rowKey="task_id"
          pagination={false}
          size="small"
        />
      </Card>

      <Modal
        title={`设备日志 - ${selectedDevice?.device_id || ''}`}
        open={logVisible}
        onCancel={() => {
          setLogVisible(false)
          setDeviceLogs([])
        }}
        footer={null}
        width={800}
      >
        {selectedDevice && (
          <div>
            <Descriptions bordered size="small" column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="设备ID">{selectedDevice.device_id}</Descriptions.Item>
              <Descriptions.Item label="任务ID">{selectedDevice.task_id}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusConfig[selectedDevice.status]?.color}>
                  {statusConfig[selectedDevice.status]?.text || selectedDevice.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="错误">
                {selectedDevice.error || '-'}
              </Descriptions.Item>
            </Descriptions>
            <div style={{
              background: '#1e1e1e',
              padding: 16,
              borderRadius: 4,
              maxHeight: 400,
              overflow: 'auto',
              fontFamily: 'monospace',
              color: '#d4d4d4',
            }}>
              {deviceLogs.length > 0 ? (
                deviceLogs.map((log, index) => (
                  <div key={index} style={{ marginBottom: 4 }}>{log}</div>
                ))
              ) : (
                <div style={{ color: '#666' }}>No logs available</div>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
