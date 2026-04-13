import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Card, Descriptions, Tag, Button, Space, Timeline, Typography, Tabs, Progress, Spin, Row, Col, Statistic, Tooltip, Form, InputNumber, message } from 'antd'
import {
  ArrowLeftOutlined,
  PlayCircleOutlined,
  LockOutlined,
  UnlockOutlined,
  FundOutlined,
  CloudOutlined,
  ThunderboltOutlined,
  FireOutlined,
  SettingOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { deviceApi, metricsApi } from '@/services/api'
import type { Device, DeviceMetrics, DeviceThresholdConfig } from '@/types'

const { Title, Text } = Typography

// Metrics thresholds
const THRESHOLDS = {
  cpu: { warning: 80, critical: 90 },
  memory: { warning: 80, critical: 95 },
  battery: { warning: 20, critical: 10 },
  temperature: { warning: 45, critical: 55 },
}

// WebSocket message types
interface WSMessage {
  type: string
  device_id?: string
  metrics?: DeviceMetrics
  [key: string]: unknown
}

// Get status color based on metric value
const getMetricStatus = (value: number, type: 'cpu' | 'memory' | 'battery' | 'temperature') => {
  const threshold = THRESHOLDS[type]
  if (type === 'battery') {
    if (value <= threshold.critical) return 'critical'
    if (value <= threshold.warning) return 'warning'
    return 'normal'
  } else {
    if (value >= threshold.critical) return 'critical'
    if (value >= threshold.warning) return 'warning'
    return 'normal'
  }
}

// Get progress color based on status
const getProgressColor = (status: string) => {
  switch (status) {
    case 'critical': return '#ff4d4f'
    case 'warning': return '#faad14'
    default: return '#52c41a'
  }
}

// Format bytes to human readable
const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// Format uptime
const formatUptime = (seconds: number) => {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

export default function DeviceDetail() {
  const { id: deviceId } = useParams<{ id: string }>()
  const navigate = useNavigate()

  // Device state
  const [device, setDevice] = useState<Device | null>(null)
  const [loading, setLoading] = useState(true)

  // Metrics state
  const [currentMetrics, setCurrentMetrics] = useState<DeviceMetrics | null>(null)
  const [metricsHistory, setMetricsHistory] = useState<DeviceMetrics[]>([])
  const [metricsLoading, setMetricsLoading] = useState(true)
  const [wsConnected, setWsConnected] = useState(false)

  // Threshold config state
  const [thresholdConfig, setThresholdConfig] = useState<DeviceThresholdConfig | null>(null)
  const [thresholdLoading, setThresholdLoading] = useState(false)
  const [thresholdSaving, setThresholdSaving] = useState(false)
  const [thresholdForm] = Form.useForm()

  const wsRef = useRef<WebSocket | null>(null)
  const metricsHistoryRef = useRef<DeviceMetrics[]>([])

  // Fetch device details
  useEffect(() => {
    const fetchDevice = async () => {
      if (!deviceId) return
      try {
        setLoading(true)
        const response = await deviceApi.getDetail(deviceId)
        setDevice(response.data)
      } catch (error) {
        console.error('Failed to fetch device:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchDevice()
  }, [deviceId])

  // Fetch metrics for the device
  const fetchMetrics = useCallback(async () => {
    if (!deviceId) return
    try {
      setMetricsLoading(true)
      // Get current metrics
      const metricsResponse = await metricsApi.getDevice(deviceId)
      setCurrentMetrics(metricsResponse.data)

      // Get history (last 5 minutes)
      const historyResponse = await metricsApi.getHistory(deviceId, { hours: 0.1 }) // 6 minutes
      const history = historyResponse.data || []
      setMetricsHistory(history)
      metricsHistoryRef.current = history
    } catch (error) {
      console.error('Failed to fetch metrics:', error)
    } finally {
      setMetricsLoading(false)
    }
  }, [deviceId])

  // WebSocket connection for real-time metrics
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/v1/devices/ws`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('WebSocket connected for metrics')
      setWsConnected(true)

      // Subscribe to this device's metrics updates
      if (deviceId) {
        ws.send(JSON.stringify({
          type: 'subscribe_metrics',
          device_ids: [deviceId]
        }))
      }
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
      setWsConnected(false)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    ws.onmessage = (event) => {
      try {
        const message: WSMessage = JSON.parse(event.data)

        if (message.type === 'metrics_update') {
          // Handle single device update
          if (message.device_id === deviceId && message.metrics) {
            setCurrentMetrics(message.metrics)

            // Update history (keep last 60 points = 5 min at 5s interval)
            const newHistory = [...metricsHistoryRef.current, message.metrics].slice(-60)
            metricsHistoryRef.current = newHistory
            setMetricsHistory(newHistory)
          }
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }

    return () => {
      // Cleanup: unsubscribe and close WebSocket
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'unsubscribe_metrics' }))
      }
      ws.close()
    }
  }, [deviceId])

  // Fetch initial metrics
  useEffect(() => {
    fetchMetrics()
  }, [fetchMetrics])

  // Fetch threshold config
  const fetchThresholdConfig = useCallback(async () => {
    if (!deviceId) return
    try {
      setThresholdLoading(true)
      const response = await metricsApi.getThresholds(deviceId)
      setThresholdConfig(response.data)
      thresholdForm.setFieldsValue(response.data)
    } catch (error) {
      console.error('Failed to fetch threshold config:', error)
    } finally {
      setThresholdLoading(false)
    }
  }, [deviceId, thresholdForm])

  useEffect(() => {
    fetchThresholdConfig()
  }, [fetchThresholdConfig])

  // Save threshold config
  const handleSaveThreshold = async (values: DeviceThresholdConfig) => {
    if (!deviceId) return
    try {
      setThresholdSaving(true)
      const response = await metricsApi.updateThresholds(deviceId, values)
      setThresholdConfig(response.data)
      message.success('阈值配置已保存')
    } catch (error) {
      console.error('Failed to save threshold config:', error)
      message.error('保存失败')
    } finally {
      setThresholdSaving(false)
    }
  }

  // Reset threshold config
  const handleResetThreshold = async () => {
    if (!deviceId) return
    try {
      setThresholdSaving(true)
      const response = await metricsApi.resetThresholds(deviceId)
      setThresholdConfig(response.data)
      thresholdForm.setFieldsValue(response.data)
      message.success('阈值配置已重置为默认值')
    } catch (error) {
      console.error('Failed to reset threshold config:', error)
      message.error('重置失败')
    } finally {
      setThresholdSaving(false)
    }
  }

  // Resubscribe when device changes
  useEffect(() => {
    if (wsRef.current && wsConnected && deviceId) {
      wsRef.current.send(JSON.stringify({
        type: 'subscribe_metrics',
        device_ids: [deviceId]
      }))
    }
  }, [deviceId, wsConnected])

  const statusConfig: Record<string, { color: string; text: string }> = {
    online: { color: 'green', text: '在线' },
    offline: { color: 'default', text: '离线' },
    busy: { color: 'orange', text: '占用中' },
    maintaining: { color: 'red', text: '维护中' },
  }

  // Chart options for CPU/Memory mini trend
  const getCpuMemoryMiniChartOption = (): EChartsOption => {
    const times = metricsHistory.map(m => new Date(m.timestamp).toLocaleTimeString())
    const cpuData = metricsHistory.map(m => m.cpu_usage?.toFixed(1) || 0)
    const memoryData = metricsHistory.map(m => m.memory_usage?.toFixed(1) || 0)

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' }
      },
      legend: {
        data: ['CPU', '内存'],
        top: 0,
        textStyle: { fontSize: 10 }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: 30,
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: times,
        axisLabel: { show: false },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%', fontSize: 10 },
        splitLine: { lineStyle: { type: 'dashed' } }
      },
      series: [
        {
          name: 'CPU',
          type: 'line',
          smooth: true,
          symbol: 'none',
          data: cpuData,
          lineStyle: { color: '#1890ff', width: 2 },
          areaStyle: { color: 'rgba(24, 144, 255, 0.1)' }
        },
        {
          name: '内存',
          type: 'line',
          smooth: true,
          symbol: 'none',
          data: memoryData,
          lineStyle: { color: '#52c41a', width: 2 },
          areaStyle: { color: 'rgba(82, 196, 26, 0.1)' }
        }
      ]
    }
  }

  // Chart options for Battery mini trend
  const getBatteryMiniChartOption = (): EChartsOption => {
    const times = metricsHistory.map(m => new Date(m.timestamp).toLocaleTimeString())
    const batteryData = metricsHistory.map(m => m.battery_level)

    return {
      tooltip: { trigger: 'axis' },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: 10,
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: times,
        axisLabel: { show: false },
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: { fontSize: 10 },
        splitLine: { lineStyle: { type: 'dashed' } }
      },
      series: [
        {
          type: 'line',
          smooth: true,
          symbol: 'none',
          data: batteryData,
          lineStyle: { color: '#52c41a', width: 2 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(82, 196, 26, 0.3)' },
                { offset: 1, color: 'rgba(82, 196, 26, 0.05)' }
              ]
            }
          }
        }
      ]
    }
  }

  // Metrics Tab Content
  const MetricsTabContent = () => {
    if (metricsLoading && !currentMetrics) {
      return (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin size="large" />
        </div>
      )
    }

    if (!currentMetrics) {
      return (
        <Card>
          <Text type="secondary">暂无指标数据，设备可能离线或尚未采集指标</Text>
        </Card>
      )
    }

    return (
      <div style={{ padding: '0 0 16px' }}>
        {/* WebSocket Status */}
        <div style={{ marginBottom: 16 }}>
          <Tag color={wsConnected ? 'green' : 'red'}>
            {wsConnected ? '实时更新已连接' : '实时更新断开'}
          </Tag>
          <Text type="secondary" style={{ marginLeft: 8 }}>
            最近更新: {new Date(currentMetrics.timestamp).toLocaleString()}
          </Text>
        </div>

        {/* Current Metrics Cards */}
        <Row gutter={16}>
          <Col span={6}>
            <Card size="small" className="metric-card">
              <div style={{ textAlign: 'center' }}>
                <FundOutlined style={{ fontSize: 20, color: '#1890ff', marginBottom: 8 }} />
                <div style={{ marginBottom: 8 }}>CPU 使用率</div>
                <Progress
                  type="dashboard"
                  width={80}
                  percent={currentMetrics.cpu_usage}
                  strokeColor={getProgressColor(getMetricStatus(currentMetrics.cpu_usage, 'cpu'))}
                  format={(percent) => (
                    <span style={{
                      color: getProgressColor(getMetricStatus(currentMetrics.cpu_usage, 'cpu')),
                      fontWeight: 'bold',
                      fontSize: 14
                    }}>
                      {percent?.toFixed(1)}%
                    </span>
                  )}
                />
                {currentMetrics.cpu_temperature && (
                  <Tooltip title="CPU 温度">
                    <Tag color={getMetricStatus(currentMetrics.cpu_temperature, 'temperature') === 'normal' ? 'green' :
                      getMetricStatus(currentMetrics.cpu_temperature, 'temperature') === 'warning' ? 'orange' : 'red'}>
                      {currentMetrics.cpu_temperature.toFixed(1)}°C
                    </Tag>
                  </Tooltip>
                )}
              </div>
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" className="metric-card">
              <div style={{ textAlign: 'center' }}>
                <CloudOutlined style={{ fontSize: 20, color: '#52c41a', marginBottom: 8 }} />
                <div style={{ marginBottom: 8 }}>内存使用率</div>
                <Progress
                  type="dashboard"
                  width={80}
                  percent={currentMetrics.memory_usage}
                  strokeColor={getProgressColor(getMetricStatus(currentMetrics.memory_usage, 'memory'))}
                  format={(percent) => (
                    <span style={{
                      color: getProgressColor(getMetricStatus(currentMetrics.memory_usage, 'memory')),
                      fontWeight: 'bold',
                      fontSize: 14
                    }}>
                      {percent?.toFixed(1)}%
                    </span>
                  )}
                />
                {currentMetrics.memory_used_mb && currentMetrics.memory_total_mb && (
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {currentMetrics.memory_used_mb}MB / {currentMetrics.memory_total_mb}MB
                  </Text>
                )}
              </div>
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" className="metric-card">
              <div style={{ textAlign: 'center' }}>
                <ThunderboltOutlined style={{ fontSize: 20, color: '#faad14', marginBottom: 8 }} />
                <div style={{ marginBottom: 8 }}>电池</div>
                <Progress
                  type="dashboard"
                  width={80}
                  percent={currentMetrics.battery_level}
                  strokeColor={getProgressColor(getMetricStatus(currentMetrics.battery_level, 'battery'))}
                  format={(percent) => (
                    <span style={{
                      color: getProgressColor(getMetricStatus(currentMetrics.battery_level, 'battery')),
                      fontWeight: 'bold',
                      fontSize: 14
                    }}>
                      {percent}%
                    </span>
                  )}
                />
                <div>
                  <Tag color={
                    currentMetrics.battery_status === 'charging' ? 'blue' :
                    currentMetrics.battery_status === 'full' ? 'green' :
                    currentMetrics.battery_status === 'discharging' ? 'orange' : 'default'
                  }>
                    {currentMetrics.battery_status}
                  </Tag>
                </div>
              </div>
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" className="metric-card">
              <div style={{ textAlign: 'center' }}>
                <FireOutlined style={{ fontSize: 20, color: '#ff4d4f', marginBottom: 8 }} />
                <div style={{ marginBottom: 8 }}>网络</div>
                <Row gutter={8}>
                  <Col span={12}>
                    <Statistic
                      title="下载"
                      value={(currentMetrics.network_rx_speed_kbps / 1024).toFixed(2)}
                      suffix="MB/s"
                      valueStyle={{ fontSize: 14 }}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title="上传"
                      value={(currentMetrics.network_tx_speed_kbps / 1024).toFixed(2)}
                      suffix="MB/s"
                      valueStyle={{ fontSize: 14 }}
                    />
                  </Col>
                </Row>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  总: ↓{formatBytes(currentMetrics.network_rx_bytes)} ↑{formatBytes(currentMetrics.network_tx_bytes)}
                </Text>
              </div>
            </Card>
          </Col>
        </Row>

        {/* Mini Trend Charts */}
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={12}>
            <Card size="small" title="CPU & 内存趋势 (最近5分钟)">
              <ReactECharts
                option={getCpuMemoryMiniChartOption()}
                style={{ height: 150 }}
                opts={{ renderer: 'canvas' }}
              />
            </Card>
          </Col>
          <Col span={12}>
            <Card size="small" title="电池趋势 (最近5分钟)">
              <ReactECharts
                option={getBatteryMiniChartOption()}
                style={{ height: 150 }}
                opts={{ renderer: 'canvas' }}
              />
            </Card>
          </Col>
        </Row>

        {/* Device Temperature */}
        {currentMetrics.device_temperature && (
          <Card size="small" style={{ marginTop: 16 }}>
            <Row gutter={16}>
              <Col span={12}>
                <Statistic
                  title="设备温度"
                  value={currentMetrics.device_temperature.toFixed(1)}
                  suffix="°C"
                  valueStyle={{
                    color: getProgressColor(getMetricStatus(currentMetrics.device_temperature, 'temperature'))
                  }}
                />
                <Tooltip title={`警告阈值: ${THRESHOLDS.temperature.warning}°C, 危险阈值: ${THRESHOLDS.temperature.critical}°C`}>
                  <Tag color={
                    getMetricStatus(currentMetrics.device_temperature, 'temperature') === 'normal' ? 'green' :
                    getMetricStatus(currentMetrics.device_temperature, 'temperature') === 'warning' ? 'orange' : 'red'
                  }>
                    {
                      getMetricStatus(currentMetrics.device_temperature, 'temperature') === 'normal' ? '正常' :
                      getMetricStatus(currentMetrics.device_temperature, 'temperature') === 'warning' ? '警告' : '危险'
                    }
                  </Tag>
                </Tooltip>
              </Col>
              {currentMetrics.uptime_seconds && (
                <Col span={12}>
                  <Statistic
                    title="运行时间"
                    value={formatUptime(currentMetrics.uptime_seconds)}
                  />
                </Col>
              )}
            </Row>
          </Card>
        )}
      </div>
    )
  }

  // Device Info Tab Content
  const DeviceInfoTabContent = () => {
    if (!device) return null

    const { color, text } = statusConfig[device.status] || { color: 'default', text: '未知' }

    return (
      <div>
        <Descriptions bordered column={2}>
          <Descriptions.Item label="设备ID">{device.id}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={color}>{text}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="品牌">{device.brand}</Descriptions.Item>
          <Descriptions.Item label="型号">{device.model}</Descriptions.Item>
          <Descriptions.Item label="操作系统">{device.os}</Descriptions.Item>
          <Descriptions.Item label="系统版本">{device.osVersion}</Descriptions.Item>
          <Descriptions.Item label="分辨率">{device.screenResolution}</Descriptions.Item>
          <Descriptions.Item label="屏幕尺寸">{device.screenSize}英寸</Descriptions.Item>
          <Descriptions.Item label="CPU">{device.cpu}</Descriptions.Item>
          <Descriptions.Item label="内存">{device.memory}</Descriptions.Item>
          <Descriptions.Item label="存储">{device.storage}</Descriptions.Item>
          <Descriptions.Item label="电量">{device.batteryLevel}%</Descriptions.Item>
          <Descriptions.Item label="最后活跃">{device.lastActiveAt}</Descriptions.Item>
          <Descriptions.Item label="标签">
            {device.tags.map((tag: string) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </Descriptions.Item>
        </Descriptions>

        <Space style={{ marginTop: 24 }}>
          <Button type="primary" icon={<PlayCircleOutlined />}>
            开始投屏
          </Button>
          {device.status === 'online' ? (
            <Button icon={<LockOutlined />}>占用设备</Button>
          ) : device.status === 'busy' ? (
            <Button icon={<UnlockOutlined />}>释放设备</Button>
          ) : null}
        </Space>
      </div>
    )
  }

  // History Tab Content
  const HistoryTabContent = () => {
    return (
      <Card title="操作历史">
        <Timeline
          items={[
            { children: '用户张三 占用了设备 - 2024-01-15 09:00:00' },
            { children: '执行了测试脚本 login_test.py - 2024-01-15 09:30:00' },
            { children: '用户张三 释放了设备 - 2024-01-15 10:00:00' },
            { children: '设备状态更新为在线 - 2024-01-15 10:30:00' },
          ]}
        />
      </Card>
    )
  }

  // Threshold Config Tab Content
  const ThresholdTabContent = () => {
    if (thresholdLoading) {
      return (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin size="large" />
        </div>
      )
    }

    return (
      <div>
        <Card title="指标告警阈值配置" style={{ marginBottom: 16 }}>
          <p style={{ marginBottom: 16, color: '#666' }}>
            配置设备性能指标的告警阈值。当指标超过阈值时，系统会触发相应级别的告警通知。
          </p>
          <Form
            form={thresholdForm}
            layout="vertical"
            onFinish={handleSaveThreshold}
            initialValues={thresholdConfig || undefined}
          >
            <Row gutter={24}>
              {/* CPU Thresholds */}
              <Col span={12}>
                <Card size="small" title={<><FundOutlined /> CPU 使用率</>} style={{ marginBottom: 16 }}>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item
                        name="cpu_warning"
                        label="警告阈值 (%)"
                        rules={[{ required: true, message: '请输入警告阈值' }]}
                      >
                        <InputNumber min={0} max={100} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="cpu_critical"
                        label="严重阈值 (%)"
                        rules={[{ required: true, message: '请输入严重阈值' }]}
                      >
                        <InputNumber min={0} max={100} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                </Card>
              </Col>

              {/* Memory Thresholds */}
              <Col span={12}>
                <Card size="small" title={<><CloudOutlined /> 内存使用率</>} style={{ marginBottom: 16 }}>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item
                        name="memory_warning"
                        label="警告阈值 (%)"
                        rules={[{ required: true, message: '请输入警告阈值' }]}
                      >
                        <InputNumber min={0} max={100} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="memory_critical"
                        label="严重阈值 (%)"
                        rules={[{ required: true, message: '请输入严重阈值' }]}
                      >
                        <InputNumber min={0} max={100} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                </Card>
              </Col>

              {/* Battery Thresholds */}
              <Col span={12}>
                <Card size="small" title={<><ThunderboltOutlined /> 电池电量</>} style={{ marginBottom: 16 }}>
                  <p style={{ fontSize: 12, color: '#999', marginBottom: 8 }}>
                    注意：电池阈值为下限值，低于阈值时触发告警
                  </p>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item
                        name="battery_warning"
                        label="警告阈值 (%)"
                        rules={[{ required: true, message: '请输入警告阈值' }]}
                      >
                        <InputNumber min={0} max={100} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="battery_critical"
                        label="严重阈值 (%)"
                        rules={[{ required: true, message: '请输入严重阈值' }]}
                      >
                        <InputNumber min={0} max={100} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                </Card>
              </Col>

              {/* Temperature Thresholds */}
              <Col span={12}>
                <Card size="small" title={<><FireOutlined /> 设备温度</>} style={{ marginBottom: 16 }}>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Form.Item
                        name="temperature_warning"
                        label="警告阈值 (°C)"
                        rules={[{ required: true, message: '请输入警告阈值' }]}
                      >
                        <InputNumber min={0} max={100} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="temperature_critical"
                        label="严重阈值 (°C)"
                        rules={[{ required: true, message: '请输入严重阈值' }]}
                      >
                        <InputNumber min={0} max={100} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>
                </Card>
              </Col>
            </Row>

            <Space>
              <Button type="primary" htmlType="submit" loading={thresholdSaving}>
                保存配置
              </Button>
              <Button icon={<ReloadOutlined />} onClick={handleResetThreshold} loading={thresholdSaving}>
                重置为默认
              </Button>
            </Space>
          </Form>
        </Card>
      </div>
    )
  }

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!device) {
    return (
      <div style={{ padding: 24 }}>
        <Text type="secondary">设备不存在</Text>
      </div>
    )
  }

  const tabItems = [
    {
      key: 'info',
      label: '设备信息',
      children: DeviceInfoTabContent(),
    },
    {
      key: 'metrics',
      label: (
        <span>
          性能指标
          {wsConnected && <Tag color="green" style={{ marginLeft: 8 }}>实时</Tag>}
        </span>
      ),
      children: MetricsTabContent(),
    },
    {
      key: 'thresholds',
      label: (
        <span>
          <SettingOutlined /> 阈值配置
        </span>
      ),
      children: ThresholdTabContent(),
    },
    {
      key: 'history',
      label: '操作历史',
      children: HistoryTabContent(),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/devices')}>
          返回列表
        </Button>
      </Space>

      <Title level={3}>{device.name}</Title>

      <Card>
        <Tabs defaultActiveKey="info" items={tabItems} />
      </Card>
    </div>
  )
}
