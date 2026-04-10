import { Card, Tag, Progress, Space, Button } from 'antd'
import {
  MobileOutlined,
  PlayCircleOutlined,
  LockOutlined,
  UnlockOutlined,
} from '@ant-design/icons'
import type { Device } from '@/types'
import './DeviceCard.css'

interface DeviceCardProps {
  device: Device
  onOccupy: (id: string) => void
  onRelease: (id: string) => void
  onScreen: (id: string) => void
  onClick: () => void
}

export default function DeviceCard({
  device,
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

  return (
    <Card
      hoverable
      className="device-card"
      onClick={onClick}
      cover={
        <div className="device-cover">
          <MobileOutlined className="device-icon" style={{ color: device.status === 'offline' ? '#ccc' : '#1890ff' }} />
          <Tag color={color} className="status-tag">{text}</Tag>
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
