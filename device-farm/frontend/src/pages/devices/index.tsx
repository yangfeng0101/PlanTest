import { useEffect, useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Row, Col, Tag, Button, Input, Select, Space, Switch, Table, Statistic, Badge, message, Dropdown } from 'antd'
import type { MenuProps } from 'antd'
import {
  MobileOutlined,
  SearchOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  PlayCircleOutlined,
  SortAscendingOutlined,
  SortDescendingOutlined,
} from '@ant-design/icons'
import DeviceCard from '@/components/DeviceCard'
import { useDeviceStore } from '@/stores/deviceStore'
import { metricsApi } from '@/services/api'
import type { Device, DeviceMetrics } from '@/types'

const { Search } = Input
const { Option } = Select

type SortField = 'name' | 'cpu' | 'memory' | 'battery'
type SortOrder = 'asc' | 'desc'

const formatOsName = (os: string) => {
  const normalized = os.toLowerCase()
  if (normalized === 'harmony') return 'HarmonyOS'
  if (normalized === 'android') return 'Android'
  if (normalized === 'ios') return 'iOS'
  return os
}

export default function DevicesPage() {
  const navigate = useNavigate()
  const { devices, loading, viewMode, fetchDevices, setViewMode, occupyDevice, releaseDevice } = useDeviceStore()
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [perfFilter, setPerfFilter] = useState<string>('all')
  const [metricsMap, setMetricsMap] = useState<Record<string, DeviceMetrics>>({})
  const [sortField, setSortField] = useState<SortField>('name')
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Memoize online device IDs to prevent unnecessary WebSocket reconnections
  const onlineDeviceIds = devices
    .filter(d => d.status === 'online')
    .map(d => d.id)
    .sort()
    .join(',')

  useEffect(() => {
    fetchDevices()
  }, [fetchDevices])

  // Fetch initial metrics
  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const { data } = await metricsApi.getAll()
        const map: Record<string, DeviceMetrics> = {}
        data.forEach((m) => {
          map[m.device_id] = m
        })
        setMetricsMap(map)
      } catch (error) {
        console.error('Failed to fetch metrics:', error)
      }
    }
    fetchMetrics()
  }, [devices])

  // WebSocket for real-time metrics updates
  const connectWebSocket = useCallback(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = window.location.host
    const wsUrl = `${wsProtocol}//${wsHost}/api/v1/devices/ws`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      // Subscribe to all devices' metrics
      const deviceIds = onlineDeviceIds.split(',').filter(Boolean)
      if (deviceIds.length > 0 && ws.readyState === WebSocket.OPEN) {
        try {
          ws.send(JSON.stringify({
            type: 'subscribe_metrics',
            device_ids: deviceIds,
          }))
        } catch (e) {
          console.error('Failed to send subscription:', e)
        }
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'metrics' || data.type === 'metrics_update') {
          // If bulk update (metrics is a map)
          if (data.metrics && !data.device_id) {
            setMetricsMap(prev => ({
              ...prev,
              ...data.metrics
            }))
          } else {
            // Single device update
            const deviceId = data.device_id || data.id
            const metrics = data.metrics || data
            if (deviceId) {
              setMetricsMap(prev => ({
                ...prev,
                [deviceId]: metrics,
              }))
            }
          }
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }

    ws.onclose = () => {
      // Reconnect after 3 seconds
      reconnectTimeoutRef.current = setTimeout(() => {
        connectWebSocket()
      }, 3000)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  }, [onlineDeviceIds])

  useEffect(() => {
    if (devices.length > 0) {
      connectWebSocket()
    }
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
    }
  }, [connectWebSocket])

  // Filter and sort devices
  const filteredDevices = devices
    .filter((device) => {
      const matchKeyword = !keyword ||
        device.name.includes(keyword) ||
        device.model.includes(keyword) ||
        device.brand.includes(keyword)
      const matchStatus = statusFilter === 'all' || device.status === statusFilter

      // Performance filter
      const metrics = metricsMap[device.id]
      let matchPerf = true
      if (perfFilter === 'warning') {
        matchPerf = metrics && (
          metrics.cpu_usage >= 80 || metrics.memory_usage >= 80 || metrics.battery_level <= 20
        )
      } else if (perfFilter === 'critical') {
        matchPerf = metrics && (
          metrics.cpu_usage >= 90 || metrics.memory_usage >= 90 || metrics.battery_level <= 10
        )
      } else if (perfFilter === 'normal') {
        matchPerf = !metrics || (
          metrics.cpu_usage < 80 && metrics.memory_usage < 80 && metrics.battery_level > 20
        )
      }

      return matchKeyword && matchStatus && matchPerf
    })
    .sort((a, b) => {
      const metricsA = metricsMap[a.id]
      const metricsB = metricsMap[b.id]

      let valueA: number | string = 0
      let valueB: number | string = 0

      switch (sortField) {
        case 'name':
          valueA = a.name
          valueB = b.name
          break
        case 'cpu':
          valueA = metricsA?.cpu_usage ?? 0
          valueB = metricsB?.cpu_usage ?? 0
          break
        case 'memory':
          valueA = metricsA?.memory_usage ?? 0
          valueB = metricsB?.memory_usage ?? 0
          break
        case 'battery':
          valueA = metricsA?.battery_level ?? a.batteryLevel
          valueB = metricsB?.battery_level ?? b.batteryLevel
          break
      }

      if (typeof valueA === 'string' && typeof valueB === 'string') {
        return sortOrder === 'asc'
          ? valueA.localeCompare(valueB)
          : valueB.localeCompare(valueA)
      }

      return sortOrder === 'asc'
        ? (valueA as number) - (valueB as number)
        : (valueB as number) - (valueA as number)
    })

  const handleOccupy = async (id: string) => {
    await occupyDevice(id)
    message.success('设备占用成功')
  }

  const handleRelease = async (id: string) => {
    await releaseDevice(id)
    message.success('设备释放成功')
  }

  const handleScreen = (id: string) => {
    window.open(`/screen?deviceId=${encodeURIComponent(id)}`, '_blank', 'noopener,noreferrer')
  }

  const onlineCount = devices.filter((d) => d.status === 'online').length
  const busyCount = devices.filter((d) => d.status === 'busy').length
  const offlineCount = devices.filter((d) => d.status === 'offline').length

  // Count devices with performance issues
  const warningCount = devices.filter((d) => {
    const m = metricsMap[d.id]
    return m && (m.cpu_usage >= 80 || m.memory_usage >= 80 || m.battery_level <= 20)
  }).length
  const criticalCount = devices.filter((d) => {
    const m = metricsMap[d.id]
    return m && (m.cpu_usage >= 90 || m.memory_usage >= 90 || m.battery_level <= 10)
  }).length

  // Get color for metric value
  const getMetricColor = (value: number, type: 'cpu' | 'memory' | 'battery') => {
    if (type === 'battery') {
      if (value <= 10) return '#ff4d4f'
      if (value <= 20) return '#faad14'
      return '#52c41a'
    }
    if (value >= 90) return '#ff4d4f'
    if (value >= 80) return '#faad14'
    return '#52c41a'
  }

  // Sort dropdown menu items
  const sortMenuItems: MenuProps['items'] = [
    {
      key: 'name',
      label: '按名称排序',
      onClick: () => { setSortField('name') },
    },
    { type: 'divider' },
    {
      key: 'cpu',
      label: '按 CPU 使用率',
      onClick: () => { setSortField('cpu') },
    },
    {
      key: 'memory',
      label: '按内存使用率',
      onClick: () => { setSortField('memory') },
    },
    {
      key: 'battery',
      label: '按电量',
      onClick: () => { setSortField('battery') },
    },
  ]

  const columns = [
    {
      title: '设备名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: Device) => (
        <a onClick={() => navigate(`/devices/${record.id}`)}>{name}</a>
      ),
    },
    {
      title: '型号',
      dataIndex: 'model',
      key: 'model',
    },
    {
      title: '品牌',
      dataIndex: 'brand',
      key: 'brand',
    },
    {
      title: '系统版本',
      dataIndex: 'osVersion',
      key: 'osVersion',
      render: (_: string, record: Device) => `${formatOsName(record.os)} ${record.osVersion}`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const colorMap: Record<string, string> = {
          online: 'green',
          offline: 'default',
          busy: 'orange',
          maintaining: 'red',
        }
        const textMap: Record<string, string> = {
          online: '在线',
          offline: '离线',
          busy: '占用中',
          maintaining: '维护中',
        }
        return <Tag color={colorMap[status]}>{textMap[status]}</Tag>
      },
    },
    {
      title: 'CPU',
      key: 'cpu_usage',
      width: 100,
      render: (_: unknown, record: Device) => {
        const metrics = metricsMap[record.id]
        if (!metrics || record.status !== 'online') return '-'
        return (
          <span style={{ color: getMetricColor(metrics.cpu_usage, 'cpu') }}>
            {metrics.cpu_usage.toFixed(0)}%
          </span>
        )
      },
    },
    {
      title: '内存',
      key: 'memory_usage',
      width: 100,
      render: (_: unknown, record: Device) => {
        const metrics = metricsMap[record.id]
        if (!metrics || record.status !== 'online') return '-'
        return (
          <span style={{ color: getMetricColor(metrics.memory_usage, 'memory') }}>
            {metrics.memory_usage.toFixed(0)}%
          </span>
        )
      },
    },
    {
      title: '电量',
      dataIndex: 'batteryLevel',
      key: 'batteryLevel',
      width: 80,
      render: (level: number, record: Device) => {
        const metrics = metricsMap[record.id]
        const batteryLevel = metrics?.battery_level ?? level
        return (
          <span style={{ color: getMetricColor(batteryLevel, 'battery') }}>
            {batteryLevel}%
          </span>
        )
      },
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: Device) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => handleScreen(record.id)}
            icon={<PlayCircleOutlined />}
          >
            投屏
          </Button>
          {record.status === 'online' && (
            <Button type="link" size="small" onClick={() => handleOccupy(record.id)}>
              占用
            </Button>
          )}
          {record.status === 'busy' && (
            <Button type="link" size="small" onClick={() => handleRelease(record.id)}>
              释放
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Row gutter={16}>
          <Col span={6}>
            <Card>
              <Statistic
                title="设备总数"
                value={devices.length}
                prefix={<MobileOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="在线设备"
                value={onlineCount}
                valueStyle={{ color: '#52c41a' }}
                prefix={<Badge status="success" />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="占用中"
                value={busyCount}
                valueStyle={{ color: '#faad14' }}
                prefix={<Badge status="warning" />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="离线设备"
                value={offlineCount}
                valueStyle={{ color: '#999' }}
                prefix={<Badge status="default" />}
              />
            </Card>
          </Col>
        </Row>
      </div>

      {/* Performance warning summary */}
      {(warningCount > 0 || criticalCount > 0) && (
        <Card style={{ marginBottom: 24, borderColor: criticalCount > 0 ? '#ff4d4f' : '#faad14' }}>
          <Space>
            {criticalCount > 0 && (
              <Tag color="error">{criticalCount} 台设备存在严重性能问题</Tag>
            )}
            {warningCount > 0 && (
              <Tag color="warning">{warningCount} 台设备存在性能警告</Tag>
            )}
          </Space>
        </Card>
      )}

      <Card>
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <Space wrap>
            <Search
              placeholder="搜索设备名称/型号/品牌"
              allowClear
              style={{ width: 280 }}
              onSearch={setKeyword}
              prefix={<SearchOutlined />}
            />
            <Select
              value={statusFilter}
              style={{ width: 120 }}
              onChange={setStatusFilter}
            >
              <Option value="all">全部状态</Option>
              <Option value="online">在线</Option>
              <Option value="busy">占用中</Option>
              <Option value="offline">离线</Option>
              <Option value="maintaining">维护中</Option>
            </Select>
            <Select
              value={perfFilter}
              style={{ width: 130 }}
              onChange={setPerfFilter}
            >
              <Option value="all">全部性能</Option>
              <Option value="normal">正常</Option>
              <Option value="warning">性能警告</Option>
              <Option value="critical">严重异常</Option>
            </Select>
          </Space>
          <Space>
            <Dropdown menu={{ items: sortMenuItems }} trigger={['click']}>
              <Button>
                {sortField === 'name' ? '排序' : sortField === 'cpu' ? 'CPU' : sortField === 'memory' ? '内存' : '电量'}
                {sortOrder === 'asc' ? <SortAscendingOutlined /> : <SortDescendingOutlined />}
              </Button>
            </Dropdown>
            <Button
              onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
              icon={sortOrder === 'asc' ? <SortAscendingOutlined /> : <SortDescendingOutlined />}
            >
              {sortOrder === 'asc' ? '升序' : '降序'}
            </Button>
            <Switch
              checked={viewMode === 'card'}
              onChange={(checked) => setViewMode(checked ? 'card' : 'list')}
              checkedChildren={<AppstoreOutlined />}
              unCheckedChildren={<UnorderedListOutlined />}
            />
          </Space>
        </div>

        {viewMode === 'card' ? (
          <Row gutter={[16, 16]}>
            {filteredDevices.map((device) => (
              <Col key={device.id} xs={24} sm={12} md={8} lg={6}>
                <DeviceCard
                  device={device}
                  metrics={metricsMap[device.id]}
                  onOccupy={handleOccupy}
                  onRelease={handleRelease}
                  onScreen={handleScreen}
                  onClick={() => navigate(`/devices/${device.id}`)}
                />
              </Col>
            ))}
          </Row>
        ) : (
          <Table
            columns={columns}
            dataSource={filteredDevices}
            rowKey="id"
            loading={loading}
            pagination={{ pageSize: 10 }}
          />
        )}
      </Card>
    </div>
  )
}
