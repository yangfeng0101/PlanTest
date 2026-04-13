import { Card, Tag, Progress, Space, Button, Tooltip, Row, Col } from 'antd'
import {
  MobileOutlined,
  PlayCircleOutlined,
  LockOutlined,
  UnlockOutlined,
  FundOutlined,
  CloudOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import type { Device, DeviceMetrics } from '@/types'
import './DeviceCard.css'

interface DeviceCardProps {
  device: Device
  metrics?: DeviceMetrics | null
  onOccupy: (id: string) => void
  onRelease: (id: string) => void
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

export default function DeviceCard({
  device,
  metrics,
  onOccupy,
  onRelease,
  onScreen,
  onClick,
}: DeviceCardProps) {
  const statusConfig: Record<string, { color: string; text: string }> = {
    online: { color: 'green', text: '在线' },
    offline: { color: 'default', text: '离线' },
    busy: { color: 'orange', text: '占用中' },
    maintaining: { color: 'red', text: '维护中' },
  }

  const { color, text } = statusConfig[device.status] || { color: 'default', text: '未知' }

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
          disabled={device.status === 'offline'}
        >
          投屏
        </Button>,
        device.status === 'online' ? (
          <Button
            key="occupy"
            type="text"
            icon={<LockOutlined />}
            onClick={(e) => {
              e.stopPropagation()
              onOccupy(device.id)
            }}
          >
            占用
          </Button>
        ) : device.status === 'busy' ? (
          <Button
            key="release"
            type="text"
            icon={<UnlockOutlined />}
            onClick={(e) => {
              e.stopPropagation()
              onRelease(device.id)
            }}
          >
            释放
          </Button>
        ) : null,
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
              <span>{device.os} {device.osVersion}</span>
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
                  percent={device.batteryLevel}
                  size="small"
                  status={device.batteryLevel < 20 ? 'exception' : 'normal'}
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
