import { useState, useEffect, useRef, useCallback } from 'react'
import { Card, Row, Col, Select, Spin, Statistic, Progress, Tag, Empty, Tooltip, Typography, Button, Modal, DatePicker, Checkbox, message } from 'antd'
import {
  DashboardOutlined,
  MobileOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  FundOutlined,
  CloudOutlined,
  ThunderboltOutlined,
  FireOutlined,
  DownloadOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { deviceApi, metricsApi } from '@/services/api'
import type { Device, DeviceMetrics } from '@/types'
import './Monitoring.css'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

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

export default function MonitoringPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null)
  const [currentMetrics, setCurrentMetrics] = useState<DeviceMetrics | null>(null)
  const [metricsHistory, setMetricsHistory] = useState<DeviceMetrics[]>([])
  const [loading, setLoading] = useState(true)
  const [wsConnected, setWsConnected] = useState(false)
  const [exportModalVisible, setExportModalVisible] = useState(false)
  const [exportDeviceIds, setExportDeviceIds] = useState<string[]>([])
  const [exportFormat, setExportFormat] = useState<'json' | 'csv'>('json')
  const [exportTimeRange, setExportTimeRange] = useState<[string, string] | null>(null)
  const [exporting, setExporting] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const metricsHistoryRef = useRef<DeviceMetrics[]>([])

  // Fetch devices on mount
  useEffect(() => {
    fetchDevices()
  }, [])

  // Fetch devices
  const fetchDevices = async () => {
    try {
      setLoading(true)
      const response = await deviceApi.getList()
      const deviceList = Array.isArray(response.data) ? response.data : (response.data as { devices: Device[] }).devices || []
      setDevices(deviceList)

      // Auto-select first online device
      const onlineDevice = deviceList.find((d: Device) => d.status === 'online')
      if (onlineDevice && !selectedDeviceId) {
        setSelectedDeviceId(onlineDevice.id)
      }
    } catch (error) {
      console.error('Failed to fetch devices:', error)
    } finally {
      setLoading(false)
    }
  }

  // Fetch metrics for selected device
  const fetchMetrics = useCallback(async () => {
    if (!selectedDeviceId) return

    try {
      // Get current metrics
      const metricsResponse = await metricsApi.getDevice(selectedDeviceId)
      setCurrentMetrics(metricsResponse.data)

      // Get history (last 5 minutes)
      const historyResponse = await metricsApi.getHistory(selectedDeviceId, { hours: 1 })
      const history = historyResponse.data || []
      setMetricsHistory(history)
      metricsHistoryRef.current = history
    } catch (error) {
      console.error('Failed to fetch metrics:', error)
    }
  }, [selectedDeviceId])

  // Fetch metrics when device changes
  useEffect(() => {
    if (selectedDeviceId) {
      fetchMetrics()
    }
  }, [selectedDeviceId, fetchMetrics])

  // WebSocket connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/v1/devices/ws`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('WebSocket connected')
      setWsConnected(true)

      // Subscribe to metrics updates
      if (selectedDeviceId) {
        ws.send(JSON.stringify({
          type: 'subscribe_metrics',
          device_ids: [selectedDeviceId]
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
          if (message.device_id === selectedDeviceId && message.metrics) {
            setCurrentMetrics(message.metrics)

            // Update history
            const newHistory = [...metricsHistoryRef.current, message.metrics].slice(-60) // Keep last 60 points (5 min at 5s interval)
            metricsHistoryRef.current = newHistory
            setMetricsHistory(newHistory)
          }

          // Handle bulk update
          if (message.metrics && typeof message.metrics === 'object' && !message.device_id) {
            const metricsMap = message.metrics as unknown as Record<string, DeviceMetrics>
            if (selectedDeviceId && metricsMap[selectedDeviceId]) {
              setCurrentMetrics(metricsMap[selectedDeviceId])

              const newHistory = [...metricsHistoryRef.current, metricsMap[selectedDeviceId]].slice(-60)
              metricsHistoryRef.current = newHistory
              setMetricsHistory(newHistory)
            }
          }
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'unsubscribe_metrics' }))
      }
      ws.close()
    }
  }, [selectedDeviceId])

  // Update WebSocket subscription when device changes
  useEffect(() => {
    if (wsRef.current && wsConnected && selectedDeviceId) {
      wsRef.current.send(JSON.stringify({
        type: 'subscribe_metrics',
        device_ids: [selectedDeviceId]
      }))
    }
  }, [selectedDeviceId, wsConnected])

  // Get device stats
  const getDeviceStats = () => {
    const total = devices.length
    const online = devices.filter(d => d.status === 'online').length
    const offline = devices.filter(d => d.status === 'offline').length
    const busy = devices.filter(d => d.status === 'busy').length
    return { total, online, offline, busy }
  }

  // Get status color
  const getMetricStatus = (value: number, type: 'cpu' | 'memory' | 'battery' | 'temperature') => {
    const threshold = THRESHOLDS[type]
    if (type === 'battery') {
      // For battery, low is bad
      if (value <= threshold.critical) return 'critical'
      if (value <= threshold.warning) return 'warning'
      return 'normal'
    } else {
      // For CPU/memory/temperature, high is bad
      if (value >= threshold.critical) return 'critical'
      if (value >= threshold.warning) return 'warning'
      return 'normal'
    }
  }

  // Get progress color
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

  // Chart options for CPU/Memory
  const getCpuMemoryChartOption = (): EChartsOption => {
    // Convert UTC timestamp to local time
    const times = metricsHistory.map(m => {
      const date = new Date(m.timestamp + 'Z') // Append Z to treat as UTC
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    })
    const cpuData = metricsHistory.map(m => m.cpu_usage?.toFixed(1) || 0)
    const memoryData = metricsHistory.map(m => m.memory_usage?.toFixed(1) || 0)

    return {
      title: {
        text: 'CPU & Memory Usage',
        left: 'center',
        textStyle: { fontSize: 14 }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' }
      },
      legend: {
        data: ['CPU', 'Memory'],
        top: 30
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: 60,
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: times
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%' }
      },
      series: [
        {
          name: 'CPU',
          type: 'line',
          smooth: true,
          data: cpuData,
          lineStyle: { color: '#1890ff' },
          areaStyle: { color: 'rgba(24, 144, 255, 0.1)' }
        },
        {
          name: 'Memory',
          type: 'line',
          smooth: true,
          data: memoryData,
          lineStyle: { color: '#52c41a' },
          areaStyle: { color: 'rgba(82, 196, 26, 0.1)' }
        }
      ]
    }
  }

  // Chart options for Network
  const getNetworkChartOption = (): EChartsOption => {
    const times = metricsHistory.map(m => {
      const date = new Date(m.timestamp + 'Z')
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    })
    const rxData = metricsHistory.map(m => (m.network_rx_speed_kbps / 1024).toFixed(2))
    const txData = metricsHistory.map(m => (m.network_tx_speed_kbps / 1024).toFixed(2))

    return {
      title: {
        text: 'Network Speed (MB/s)',
        left: 'center',
        textStyle: { fontSize: 14 }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' }
      },
      legend: {
        data: ['Download', 'Upload'],
        top: 30
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: 60,
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: times
      },
      yAxis: {
        type: 'value',
        axisLabel: { formatter: '{value}' }
      },
      series: [
        {
          name: 'Download',
          type: 'bar',
          data: rxData,
          itemStyle: { color: '#1890ff' }
        },
        {
          name: 'Upload',
          type: 'bar',
          data: txData,
          itemStyle: { color: '#faad14' }
        }
      ]
    }
  }

  // Chart options for Battery
  const getBatteryChartOption = (): EChartsOption => {
    const times = metricsHistory.map(m => {
      const date = new Date(m.timestamp + 'Z')
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    })
    const batteryData = metricsHistory.map(m => m.battery_level)

    return {
      title: {
        text: 'Battery Level (%)',
        left: 'center',
        textStyle: { fontSize: 14 }
      },
      tooltip: {
        trigger: 'axis'
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        top: 40,
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: times
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100
      },
      series: [
        {
          type: 'line',
          smooth: true,
          data: batteryData,
          lineStyle: { color: '#52c41a' },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(82, 196, 26, 0.3)' },
                { offset: 1, color: 'rgba(82, 196, 26, 0.05)' }
              ]
            }
          },
          markLine: {
            silent: true,
            data: [
              { yAxis: THRESHOLDS.battery.warning, lineStyle: { color: '#faad14' }, label: { formatter: 'Warning' } },
              { yAxis: THRESHOLDS.battery.critical, lineStyle: { color: '#ff4d4f' }, label: { formatter: 'Critical' } }
            ]
          }
        }
      ]
    }
  }

  // Handle export
  const handleExport = async () => {
    try {
      setExporting(true)
      const params: { deviceIds?: string[]; startTime?: string; endTime?: string; hours?: number; format?: 'json' | 'csv' } = {
        format: exportFormat,
      }

      if (exportDeviceIds.length > 0) {
        params.deviceIds = exportDeviceIds
      }

      if (exportTimeRange) {
        params.startTime = exportTimeRange[0]
        params.endTime = exportTimeRange[1]
      } else {
        params.hours = 1
      }

      const response = await metricsApi.export(params)

      // Create download link
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `metrics_export_${new Date().toISOString().slice(0, 10)}.${exportFormat}`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)

      message.success('数据导出成功')
      setExportModalVisible(false)
    } catch (error) {
      console.error('Export failed:', error)
      message.error('数据导出失败')
    } finally {
      setExporting(false)
    }
  }

  const stats = getDeviceStats()

  if (loading) {
    return (
      <div className="monitoring-loading">
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div className="monitoring-page">
      <div className="monitoring-header">
        <Title level={4}>
          <DashboardOutlined /> 设备监控仪表板
        </Title>
        <div className="monitoring-controls">
          <Tag color={wsConnected ? 'green' : 'red'}>
            {wsConnected ? 'WebSocket 已连接' : 'WebSocket 断开'}
          </Tag>
          <Button
            icon={<DownloadOutlined />}
            onClick={() => setExportModalVisible(true)}
          >
            导出数据
          </Button>
          <Select
            style={{ width: 250 }}
            placeholder="选择设备"
            value={selectedDeviceId}
            onChange={setSelectedDeviceId}
            showSearch
            optionFilterProp="children"
          >
            {devices.map(device => (
              <Select.Option key={device.id} value={device.id}>
                <MobileOutlined /> {device.name} ({device.model})
                <Tag
                  color={device.status === 'online' ? 'green' : device.status === 'busy' ? 'orange' : 'red'}
                  style={{ marginLeft: 8 }}
                >
                  {device.status}
                </Tag>
              </Select.Option>
            ))}
          </Select>
        </div>
      </div>

      {/* Device Overview Cards */}
      <Row gutter={16} className="device-stats">
        <Col span={6}>
          <Card>
            <Statistic
              title="设备总数"
              value={stats.total}
              prefix={<MobileOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="在线设备"
              value={stats.online}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="离线设备"
              value={stats.offline}
              prefix={<CloseCircleOutlined />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="使用中"
              value={stats.busy}
              prefix={<WarningOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Selected Device Metrics */}
      {selectedDeviceId && currentMetrics ? (
        <>
          {/* Current Metrics Cards */}
          <Row gutter={16} className="current-metrics">
            <Col span={6}>
              <Card
                className="metric-card"
                title={
                  <span>
                    <FundOutlined /> CPU 使用率
                  </span>
                }
              >
                <Progress
                  type="dashboard"
                  percent={currentMetrics.cpu_usage}
                  strokeColor={getProgressColor(getMetricStatus(currentMetrics.cpu_usage, 'cpu'))}
                  format={(percent) => (
                    <span style={{
                      color: getProgressColor(getMetricStatus(currentMetrics.cpu_usage, 'cpu')),
                      fontWeight: 'bold'
                    }}>
                      {percent?.toFixed(1)}%
                    </span>
                  )}
                />
                {currentMetrics.cpu_temperature && (
                  <Text type="secondary">温度: {currentMetrics.cpu_temperature.toFixed(1)}°C</Text>
                )}
              </Card>
            </Col>
            <Col span={6}>
              <Card
                className="metric-card"
                title={
                  <span>
                    <CloudOutlined /> 内存使用率
                  </span>
                }
              >
                <Progress
                  type="dashboard"
                  percent={currentMetrics.memory_usage}
                  strokeColor={getProgressColor(getMetricStatus(currentMetrics.memory_usage, 'memory'))}
                  format={(percent) => (
                    <span style={{
                      color: getProgressColor(getMetricStatus(currentMetrics.memory_usage, 'memory')),
                      fontWeight: 'bold'
                    }}>
                      {percent?.toFixed(1)}%
                    </span>
                  )}
                />
                {currentMetrics.memory_used_mb && currentMetrics.memory_total_mb && (
                  <Text type="secondary">
                    {currentMetrics.memory_used_mb}MB / {currentMetrics.memory_total_mb}MB
                  </Text>
                )}
              </Card>
            </Col>
            <Col span={6}>
              <Card
                className="metric-card"
                title={
                  <span>
                    <ThunderboltOutlined /> 电池
                  </span>
                }
              >
                <Progress
                  type="dashboard"
                  percent={currentMetrics.battery_level}
                  strokeColor={getProgressColor(getMetricStatus(currentMetrics.battery_level, 'battery'))}
                  format={(percent) => (
                    <span style={{
                      color: getProgressColor(getMetricStatus(currentMetrics.battery_level, 'battery')),
                      fontWeight: 'bold'
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
                  {currentMetrics.battery_temperature && (
                    <Text type="secondary"> {currentMetrics.battery_temperature.toFixed(1)}°C</Text>
                  )}
                </div>
              </Card>
            </Col>
            <Col span={6}>
              <Card
                className="metric-card"
                title={
                  <span>
                    <FireOutlined /> 网络
                  </span>
                }
              >
                <Row>
                  <Col span={12}>
                    <Statistic
                      title="下载"
                      value={(currentMetrics.network_rx_speed_kbps / 1024).toFixed(2)}
                      suffix="MB/s"
                      valueStyle={{ fontSize: 16 }}
                    />
                  </Col>
                  <Col span={12}>
                    <Statistic
                      title="上传"
                      value={(currentMetrics.network_tx_speed_kbps / 1024).toFixed(2)}
                      suffix="MB/s"
                      valueStyle={{ fontSize: 16 }}
                    />
                  </Col>
                </Row>
                <Text type="secondary">
                  总计: ↓{formatBytes(currentMetrics.network_rx_bytes)} / ↑{formatBytes(currentMetrics.network_tx_bytes)}
                </Text>
              </Card>
            </Col>
          </Row>

          {/* Metrics Charts */}
          <Row gutter={16} className="metrics-charts">
            <Col span={12}>
              <Card>
                <ReactECharts option={getCpuMemoryChartOption()} style={{ height: 300 }} />
              </Card>
            </Col>
            <Col span={12}>
              <Card>
                <ReactECharts option={getNetworkChartOption()} style={{ height: 300 }} />
              </Card>
            </Col>
          </Row>

          <Row gutter={16} className="metrics-charts">
            <Col span={12}>
              <Card>
                <ReactECharts option={getBatteryChartOption()} style={{ height: 300 }} />
              </Card>
            </Col>
            <Col span={12}>
              <Card title="设备信息">
                {currentMetrics.uptime_seconds && (
                  <Statistic
                    title="运行时间"
                    value={formatUptime(currentMetrics.uptime_seconds)}
                  />
                )}
                {currentMetrics.device_temperature && (
                  <div style={{ marginTop: 16 }}>
                    <Tooltip title={`警告阈值: ${THRESHOLDS.temperature.warning}°C, 危险阈值: ${THRESHOLDS.temperature.critical}°C`}>
                      <Text>
                        设备温度: <span style={{
                          color: getProgressColor(getMetricStatus(currentMetrics.device_temperature, 'temperature')),
                          fontWeight: 'bold'
                        }}>
                          {currentMetrics.device_temperature.toFixed(1)}°C
                        </span>
                      </Text>
                    </Tooltip>
                  </div>
                )}
              </Card>
            </Col>
          </Row>
        </>
      ) : (
        <Card className="no-device-selected">
          <Empty
            description="请选择一个设备查看详细指标"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </Card>
      )}

      {/* Export Modal */}
      <Modal
        title="导出监控数据"
        open={exportModalVisible}
        onCancel={() => setExportModalVisible(false)}
        onOk={handleExport}
        confirmLoading={exporting}
        okText="导出"
        cancelText="取消"
      >
        <div style={{ marginBottom: 16 }}>
          <Text>选择设备（不选则导出全部）：</Text>
          <Checkbox.Group
            style={{ width: '100%', marginTop: 8 }}
            value={exportDeviceIds}
            onChange={(values) => setExportDeviceIds(values as string[])}
          >
            <Row>
              {devices.map(device => (
                <Col span={12} key={device.id}>
                  <Checkbox value={device.id}>{device.name}</Checkbox>
                </Col>
              ))}
            </Row>
          </Checkbox.Group>
        </div>

        <div style={{ marginBottom: 16 }}>
          <Text>时间范围（不选则默认最近1小时）：</Text>
          <div style={{ marginTop: 8 }}>
            <RangePicker
              showTime
              style={{ width: '100%' }}
              onChange={(_, dateStrings) => {
                if (dateStrings[0] && dateStrings[1]) {
                  setExportTimeRange([dateStrings[0], dateStrings[1]])
                } else {
                  setExportTimeRange(null)
                }
              }}
            />
          </div>
        </div>

        <div>
          <Text>导出格式：</Text>
          <Select
            style={{ width: 120, marginLeft: 8 }}
            value={exportFormat}
            onChange={setExportFormat}
          >
            <Select.Option value="json">JSON</Select.Option>
            <Select.Option value="csv">CSV</Select.Option>
          </Select>
        </div>
      </Modal>
    </div>
  )
}
