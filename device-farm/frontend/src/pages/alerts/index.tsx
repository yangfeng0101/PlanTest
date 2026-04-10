import { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Select,
  InputNumber,
  message,
  Popconfirm,
  Tooltip,
  Badge,
  Tabs,
  Switch,
} from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  BellOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  AlertOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useAuthStore, hasPermission } from '@/stores/authStore'

// Alert types
type AlertType = 'device_offline' | 'task_failure_rate' | 'device_idle' | 'custom'
type AlertSeverity = 'info' | 'warning' | 'error' | 'critical'
type AlertStatus = 'active' | 'resolved' | 'acknowledged'
type NotificationChannel = 'feishu' | 'dingtalk' | 'email' | 'webhook'

// Alert Rule interface
interface AlertRule {
  id: string
  name: string
  description?: string
  alert_type: AlertType
  severity: AlertSeverity
  enabled: boolean
  threshold: number
  duration_seconds: number
  channels: NotificationChannel[]
  recipients: string[]
  cooldown_seconds: number
  created_at: string
  updated_at: string
  created_by?: string
}

// Alert interface
interface Alert {
  id: string
  rule_id: string
  rule_name: string
  alert_type: AlertType
  severity: AlertSeverity
  status: AlertStatus
  title: string
  message: string
  details: Record<string, unknown>
  device_id?: string
  task_id?: string
  triggered_at: string
  resolved_at?: string
  acknowledged_at?: string
  acknowledged_by?: string
  notifications_sent: number
  last_notification_at?: string
}

// Alert History interface
interface AlertHistory {
  id: string
  alert_id: string
  action: string
  timestamp: string
  user_id?: string
  details: Record<string, unknown>
}

// Form data interface
interface AlertRuleFormData {
  name: string
  description?: string
  alert_type: AlertType
  severity: AlertSeverity
  threshold: number
  duration_seconds: number
  channels: NotificationChannel[]
  recipients: string[]
  cooldown_seconds: number
}

const API_BASE = '/api/v1'

const getSeverityTag = (severity: AlertSeverity) => {
  const config: Record<AlertSeverity, { color: string; icon: React.ReactNode }> = {
    info: { color: 'blue', icon: <InfoCircleOutlined /> },
    warning: { color: 'orange', icon: <WarningOutlined /> },
    error: { color: 'red', icon: <CloseCircleOutlined /> },
    critical: { color: 'magenta', icon: <AlertOutlined /> },
  }
  const { color, icon } = config[severity] || config.info
  return <Tag color={color} icon={icon}>{severity.toUpperCase()}</Tag>
}

const getStatusBadge = (status: AlertStatus) => {
  const config: Record<AlertStatus, { status: 'success' | 'error' | 'warning' | 'default'; text: string }> = {
    active: { status: 'error', text: 'Active' },
    resolved: { status: 'success', text: 'Resolved' },
    acknowledged: { status: 'warning', text: 'Acknowledged' },
  }
  const { status: badgeStatus, text } = config[status] || { status: 'default', text: status }
  return <Badge status={badgeStatus} text={text} />
}

const getAlertTypeTag = (type: AlertType) => {
  const config: Record<AlertType, { color: string; text: string }> = {
    device_offline: { color: 'red', text: 'Device Offline' },
    task_failure_rate: { color: 'orange', text: 'Task Failure Rate' },
    device_idle: { color: 'blue', text: 'Device Idle' },
    custom: { color: 'purple', text: 'Custom' },
  }
  const { color, text } = config[type] || { color: 'default', text: type }
  return <Tag color={color}>{text}</Tag>
}

export default function AlertsPage() {
  const { user: currentUser, accessToken } = useAuthStore()
  const [rules, setRules] = useState<AlertRule[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [history, setHistory] = useState<AlertHistory[]>([])
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('rules')

  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [selectedRule, setSelectedRule] = useState<AlertRule | null>(null)

  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()

  // Check permission
  const canManageAlerts = hasPermission(currentUser, 'alert:write')

  const fetchWithAuth = useCallback(async (url: string, options: RequestInit = {}) => {
    if (!accessToken) {
      throw new Error('Not authenticated')
    }
    const response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || 'Request failed')
    }
    return response
  }, [accessToken])

  const fetchRules = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetchWithAuth(`${API_BASE}/alerts/rules`)
      const data = await response.json()
      setRules(data || [])
    } catch (error) {
      console.error('Failed to fetch rules:', error)
      message.error('Failed to load alert rules')
    } finally {
      setLoading(false)
    }
  }, [fetchWithAuth])

  const fetchAlerts = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetchWithAuth(`${API_BASE}/alerts?limit=100`)
      const data = await response.json()
      setAlerts(data || [])
    } catch (error) {
      console.error('Failed to fetch alerts:', error)
      message.error('Failed to load alerts')
    } finally {
      setLoading(false)
    }
  }, [fetchWithAuth])

  const fetchHistory = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetchWithAuth(`${API_BASE}/alerts/history/all?limit=100`)
      const data = await response.json()
      setHistory(data || [])
    } catch (error) {
      console.error('Failed to fetch history:', error)
      message.error('Failed to load alert history')
    } finally {
      setLoading(false)
    }
  }, [fetchWithAuth])

  useEffect(() => {
    if (activeTab === 'rules') {
      fetchRules()
    } else if (activeTab === 'alerts') {
      fetchAlerts()
    } else if (activeTab === 'history') {
      fetchHistory()
    }
  }, [activeTab, fetchRules, fetchAlerts, fetchHistory])

  const handleCreateRule = async (values: AlertRuleFormData) => {
    try {
      await fetchWithAuth(`${API_BASE}/alerts/rules`, {
        method: 'POST',
        body: JSON.stringify(values),
      })
      message.success('Alert rule created successfully')
      setCreateModalVisible(false)
      createForm.resetFields()
      fetchRules()
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to create rule'
      message.error(msg)
    }
  }

  const handleUpdateRule = async (values: Partial<AlertRuleFormData>) => {
    if (!selectedRule) return

    try {
      await fetchWithAuth(`${API_BASE}/alerts/rules/${selectedRule.id}`, {
        method: 'PUT',
        body: JSON.stringify(values),
      })
      message.success('Alert rule updated successfully')
      setEditModalVisible(false)
      editForm.resetFields()
      fetchRules()
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to update rule'
      message.error(msg)
    }
  }

  const handleDeleteRule = async (ruleId: string) => {
    try {
      await fetchWithAuth(`${API_BASE}/alerts/rules/${ruleId}`, {
        method: 'DELETE',
      })
      message.success('Alert rule deleted successfully')
      fetchRules()
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to delete rule'
      message.error(msg)
    }
  }

  const handleToggleRule = async (ruleId: string, enabled: boolean) => {
    try {
      const action = enabled ? 'enable' : 'disable'
      await fetchWithAuth(`${API_BASE}/alerts/rules/${ruleId}/${action}`, {
        method: 'POST',
      })
      message.success(`Alert rule ${action}d successfully`)
      fetchRules()
    } catch (error) {
      const msg = error instanceof Error ? error.message : `Failed to toggle rule`
      message.error(msg)
    }
  }

  const handleAcknowledgeAlert = async (alertId: string) => {
    try {
      await fetchWithAuth(`${API_BASE}/alerts/${alertId}/acknowledge?user_id=${currentUser?.id}`, {
        method: 'POST',
      })
      message.success('Alert acknowledged')
      fetchAlerts()
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to acknowledge alert'
      message.error(msg)
    }
  }

  const handleResolveAlert = async (alertId: string) => {
    try {
      await fetchWithAuth(`${API_BASE}/alerts/${alertId}/resolve?user_id=${currentUser?.id}`, {
        method: 'POST',
      })
      message.success('Alert resolved')
      fetchAlerts()
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to resolve alert'
      message.error(msg)
    }
  }

  const openEditModal = (rule: AlertRule) => {
    setSelectedRule(rule)
    editForm.setFieldsValue({
      name: rule.name,
      description: rule.description,
      alert_type: rule.alert_type,
      severity: rule.severity,
      threshold: rule.threshold,
      duration_seconds: rule.duration_seconds,
      channels: rule.channels,
      recipients: rule.recipients,
      cooldown_seconds: rule.cooldown_seconds,
    })
    setEditModalVisible(true)
  }

  // Rule columns
  const ruleColumns: ColumnsType<AlertRule> = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: 'Type',
      dataIndex: 'alert_type',
      key: 'alert_type',
      width: 150,
      render: (type: AlertType) => getAlertTypeTag(type),
    },
    {
      title: 'Severity',
      dataIndex: 'severity',
      key: 'severity',
      width: 120,
      render: (severity: AlertSeverity) => getSeverityTag(severity),
    },
    {
      title: 'Threshold',
      dataIndex: 'threshold',
      key: 'threshold',
      width: 100,
      render: (threshold: number, record) => {
        if (record.alert_type === 'task_failure_rate') {
          return `${(threshold * 100).toFixed(0)}%`
        }
        return threshold
      },
    },
    {
      title: 'Duration',
      dataIndex: 'duration_seconds',
      key: 'duration_seconds',
      width: 100,
      render: (seconds: number) => {
        if (seconds >= 3600) return `${(seconds / 3600).toFixed(0)}h`
        if (seconds >= 60) return `${(seconds / 60).toFixed(0)}m`
        return `${seconds}s`
      },
    },
    {
      title: 'Channels',
      dataIndex: 'channels',
      key: 'channels',
      width: 150,
      render: (channels: NotificationChannel[]) => (
        <Space size="small">
          {channels.map(ch => (
            <Tag key={ch}>{ch}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record) => (
        <Switch
          checked={enabled}
          onChange={(checked) => handleToggleRule(record.id, checked)}
          disabled={!canManageAlerts}
        />
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 120,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="Edit">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openEditModal(record)}
              disabled={!canManageAlerts}
            />
          </Tooltip>
          <Popconfirm
            title="Delete this rule?"
            description="This action cannot be undone."
            onConfirm={() => handleDeleteRule(record.id)}
            okText="Yes"
            cancelText="No"
            disabled={!canManageAlerts}
          >
            <Tooltip title="Delete">
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={!canManageAlerts}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  // Alert columns
  const alertColumns: ColumnsType<Alert> = [
    {
      title: 'Title',
      dataIndex: 'title',
      key: 'title',
      width: 200,
    },
    {
      title: 'Rule',
      dataIndex: 'rule_name',
      key: 'rule_name',
      width: 150,
    },
    {
      title: 'Type',
      dataIndex: 'alert_type',
      key: 'alert_type',
      width: 130,
      render: (type: AlertType) => getAlertTypeTag(type),
    },
    {
      title: 'Severity',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity: AlertSeverity) => getSeverityTag(severity),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: AlertStatus) => getStatusBadge(status),
    },
    {
      title: 'Message',
      dataIndex: 'message',
      key: 'message',
      width: 250,
      ellipsis: true,
    },
    {
      title: 'Triggered At',
      dataIndex: 'triggered_at',
      key: 'triggered_at',
      width: 180,
      render: (date: string) => date ? new Date(date).toLocaleString() : '-',
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 150,
      render: (_, record) => {
        if (record.status === 'resolved') return null
        return (
          <Space size="small">
            {record.status === 'active' && (
              <Tooltip title="Acknowledge">
                <Button
                  type="text"
                  size="small"
                  icon={<CheckCircleOutlined />}
                  onClick={() => handleAcknowledgeAlert(record.id)}
                />
              </Tooltip>
            )}
            <Tooltip title="Resolve">
              <Button
                type="text"
                size="small"
                icon={<CloseCircleOutlined />}
                onClick={() => handleResolveAlert(record.id)}
              />
            </Tooltip>
          </Space>
        )
      },
    },
  ]

  // History columns
  const historyColumns: ColumnsType<AlertHistory> = [
    {
      title: 'Alert ID',
      dataIndex: 'alert_id',
      key: 'alert_id',
      width: 150,
      ellipsis: true,
    },
    {
      title: 'Action',
      dataIndex: 'action',
      key: 'action',
      width: 150,
      render: (action: string) => {
        const colors: Record<string, string> = {
          triggered: 'red',
          resolved: 'green',
          acknowledged: 'orange',
          notification_sent: 'blue',
        }
        return <Tag color={colors[action] || 'default'}>{action}</Tag>
      },
    },
    {
      title: 'User',
      dataIndex: 'user_id',
      key: 'user_id',
      width: 120,
      render: (userId?: string) => userId || 'System',
    },
    {
      title: 'Details',
      dataIndex: 'details',
      key: 'details',
      width: 200,
      ellipsis: true,
      render: (details: Record<string, unknown>) => {
        if (!details || Object.keys(details).length === 0) return '-'
        return JSON.stringify(details)
      },
    },
    {
      title: 'Timestamp',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (date: string) => date ? new Date(date).toLocaleString() : '-',
    },
  ]

  // Common form items
  const formItems = (
    <>
      <Form.Item
        name="name"
        label="Rule Name"
        rules={[{ required: true, message: 'Please input rule name' }]}
      >
        <Input placeholder="Enter rule name" />
      </Form.Item>
      <Form.Item
        name="description"
        label="Description"
      >
        <Input.TextArea placeholder="Enter description" rows={2} />
      </Form.Item>
      <Form.Item
        name="alert_type"
        label="Alert Type"
        rules={[{ required: true, message: 'Please select alert type' }]}
      >
        <Select
          options={[
            { value: 'device_offline', label: 'Device Offline' },
            { value: 'task_failure_rate', label: 'Task Failure Rate' },
            { value: 'device_idle', label: 'Device Idle' },
            { value: 'custom', label: 'Custom' },
          ]}
        />
      </Form.Item>
      <Form.Item
        name="severity"
        label="Severity"
        initialValue="warning"
        rules={[{ required: true, message: 'Please select severity' }]}
      >
        <Select
          options={[
            { value: 'info', label: 'Info' },
            { value: 'warning', label: 'Warning' },
            { value: 'error', label: 'Error' },
            { value: 'critical', label: 'Critical' },
          ]}
        />
      </Form.Item>
      <Form.Item
        name="threshold"
        label="Threshold"
        initialValue={0}
        tooltip="For failure rate, use decimal (e.g., 0.5 for 50%)"
      >
        <InputNumber min={0} step={0.1} style={{ width: '100%' }} />
      </Form.Item>
      <Form.Item
        name="duration_seconds"
        label="Duration (seconds)"
        initialValue={300}
        tooltip="How long the condition must persist before triggering"
      >
        <InputNumber min={0} step={60} style={{ width: '100%' }} />
      </Form.Item>
      <Form.Item
        name="channels"
        label="Notification Channels"
        initialValue={['feishu']}
      >
        <Select
          mode="multiple"
          options={[
            { value: 'feishu', label: 'Feishu' },
            { value: 'dingtalk', label: 'DingTalk' },
            { value: 'email', label: 'Email' },
            { value: 'webhook', label: 'Webhook' },
          ]}
        />
      </Form.Item>
      <Form.Item
        name="recipients"
        label="Recipients"
        tooltip="Email addresses or webhook URLs"
      >
        <Select
          mode="tags"
          placeholder="Enter recipients"
          tokenSeparators={[',']}
        />
      </Form.Item>
      <Form.Item
        name="cooldown_seconds"
        label="Cooldown (seconds)"
        initialValue={300}
        tooltip="Minimum time between repeated alerts"
      >
        <InputNumber min={0} step={60} style={{ width: '100%' }} />
      </Form.Item>
    </>
  )

  return (
    <div>
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          tabBarExtraContent={
            activeTab === 'rules' && canManageAlerts && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setCreateModalVisible(true)}
              >
                Create Rule
              </Button>
            )
          }
        >
          <Tabs.TabPane
            tab={
              <span>
                <BellOutlined />
                Alert Rules
              </span>
            }
            key="rules"
          >
            <Table
              columns={ruleColumns}
              dataSource={rules}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </Tabs.TabPane>

          <Tabs.TabPane
            tab={
              <span>
                <AlertOutlined />
                Active Alerts
              </span>
            }
            key="alerts"
          >
            <Table
              columns={alertColumns}
              dataSource={alerts}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </Tabs.TabPane>

          <Tabs.TabPane
            tab={
              <span>
                <InfoCircleOutlined />
                History
              </span>
            }
            key="history"
          >
            <Table
              columns={historyColumns}
              dataSource={history}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </Tabs.TabPane>
        </Tabs>
      </Card>

      {/* Create Rule Modal */}
      <Modal
        title="Create Alert Rule"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false)
          createForm.resetFields()
        }}
        onOk={() => createForm.submit()}
        width={600}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreateRule}
        >
          {formItems}
        </Form>
      </Modal>

      {/* Edit Rule Modal */}
      <Modal
        title="Edit Alert Rule"
        open={editModalVisible}
        onCancel={() => {
          setEditModalVisible(false)
          editForm.resetFields()
        }}
        onOk={() => editForm.submit()}
        width={600}
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleUpdateRule}
        >
          {formItems}
        </Form>
      </Modal>
    </div>
  )
}
