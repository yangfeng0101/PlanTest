import { Card, Tag, Progress, Space, Button, Tooltip, Row, Col } from 'antd'
import MobileOutlined from '@ant-design/icons/MobileOutlined'
import PlayCircleOutlined from '@ant-design/icons/PlayCircleOutlined'
import FundOutlined from '@ant-design/icons/FundOutlined'
import CloudOutlined from '@ant-design/icons/CloudOutlined'
import WarningOutlined from '@ant-design/icons/WarningOutlined'
import type { Device, DeviceMetrics } from '@/types'
import { screenDebugLabel, supportsScreenDebug } from '@/utils/device'
import './DeviceCard.css'

interface DeviceCardProps {
  device: Device
  metrics?: DeviceMetrics | null
  screenActive?: boolean
  onScreen: (id: string) => void
  onClick: () => void
}

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

const formatDeviceOs = (device: Device) => {
  const name = device.displayOs || device.os
  const version = device.displayOsVersion || device.osVersion
  return `${name} ${version}`.trim()
}

export default function DeviceCard({
  device,
  metrics,
  screenActive = false,
  onScreen,
  onClick,
}: DeviceCardProps) {
  const statusConfig: Record<string, { color: string; text: string }> = {
    online: { color: 'green', text: '在线' },
    offline: { color: 'default', text: '离线' },
    busy: { color: 'orange', text: '占用中' },
    maintaining: { color: 'red', text: '维护中' },
  }

  const { color, text } = screenActive
    ? { color: 'orange', text: '占用中' }
    : statusConfig[device.status] || { color: 'default', text: '未知' }
  const batteryLevel = metrics?.battery_level ?? device.batteryLevel
  const debugLabel = screenDebugLabel(device)
  const canOpenScreenDebug = device.status === 'online' && supportsScreenDebug(device) && !screenActive
  const disabledReason = screenActive || device.status === 'busy'
    ? '设备已被投屏或任务占用'
    : device.status !== 'online'
      ? '设备当前不可用'
      : undefined

  // Check if device has abnormal metrics
  const hasWarning = metrics && (
    metrics.cpu_usage >= 80 ||
    metrics.memory_usage >= 80 ||
    metrics.battery_level <= 20
  )

  const hasCritical = metrics && (
    metrics.cpu_usage >= 90 ||
    metrics.memory_usage >= 90 ||
    metrics.battery_level <= 10
  )

  return (
    <Card
      hoverable
      className={`device-card ${hasCritical ? 'device-card-critical' : hasWarning ? 'device-card-warning' : ''}`}
      onClick={onClick}
      cover={
        <div className="device-cover">
          <MobileOutlined className="device-icon" style={{ color: device.status === 'offline' ? '#ccc' : '#1890ff' }} />
          <Tag color={color} className="status-tag">{text}</Tag>
          {hasCritical && (
            <Tooltip title="设备存在严重性能问题">
              <WarningOutlined style={{ color: '#ff4d4f', marginLeft: 8 }} />
            </Tooltip>
          )}
        </div>
      }
      actions={[
        <Button
          key="screen"
          type="text"
          icon={<PlayCircleOutlined />}
          onClick={(e) => {
            e.stopPropagation()
            onScreen(device.id)
          }}
          disabled={!canOpenScreenDebug}
          title={disabledReason}
        >
          {screenActive || device.status === 'busy' ? '占用中' : debugLabel}
        </Button>,
      ]}
    >
      <Card.Meta
        title={device.name}
        description={
          <div className="device-info">
            <div className="device-meta">
              <span>{device.brand}</span>
              <span>{device.model}</span>
            </div>
            <div className="device-meta">
              <span>{formatDeviceOs(device)}</span>
            </div>
            <Space direction="vertical" style={{ width: '100%', marginTop: 8 }}>
              {/* Performance metrics mini indicators */}
              {metrics && device.status === 'online' && (
                <Row gutter={8} style={{ marginBottom: 8 }}>
                  <Col span={12}>
                    <Tooltip title={`CPU 使用率: ${metrics.cpu_usage.toFixed(1)}%`}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <FundOutlined style={{ fontSize: 12, color: '#999' }} />
                        <Progress
                          percent={metrics.cpu_usage}
                          size="small"
                          showInfo={false}
                          strokeColor={getMetricColor(metrics.cpu_usage, 'cpu')}
                          style={{ flex: 1 }}
                        />
                        <span style={{ fontSize: 11, color: getMetricColor(metrics.cpu_usage, 'cpu') }}>
                          {metrics.cpu_usage.toFixed(0)}%
                        </span>
                      </div>
                    </Tooltip>
                  </Col>
                  <Col span={12}>
                    <Tooltip title={`内存使用率: ${metrics.memory_usage.toFixed(1)}%`}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <CloudOutlined style={{ fontSize: 12, color: '#999' }} />
                        <Progress
                          percent={metrics.memory_usage}
                          size="small"
                          showInfo={false}
                          strokeColor={getMetricColor(metrics.memory_usage, 'memory')}
                          style={{ flex: 1 }}
                        />
                        <span style={{ fontSize: 11, color: getMetricColor(metrics.memory_usage, 'memory') }}>
                          {metrics.memory_usage.toFixed(0)}%
                        </span>
                      </div>
                    </Tooltip>
                  </Col>
                </Row>
              )}
              {/* Battery info */}
              <div className="battery-info">
                <span>电量</span>
                <Progress
                  percent={batteryLevel}
                  size="small"
                  status={batteryLevel < 20 ? 'exception' : 'normal'}
                />
              </div>
            </Space>
            {device.tags.length > 0 && (
              <div className="device-tags">
                {device.tags.slice(0, 3).map((tag) => (
                  <Tag key={tag} style={{ marginBottom: 4 }}>{tag}</Tag>
                ))}
              </div>
            )}
          </div>
        }
      />
    </Card>
  )
}
