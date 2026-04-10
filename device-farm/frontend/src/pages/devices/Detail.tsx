import { useParams, useNavigate } from 'react-router-dom'
import { Card, Descriptions, Tag, Button, Space, Timeline, Typography } from 'antd'
import { ArrowLeftOutlined, PlayCircleOutlined, LockOutlined, UnlockOutlined } from '@ant-design/icons'
import type { Device } from '@/types'

const { Title } = Typography

// Mock data - will be replaced with API call
const mockDevice: Device = {
  id: 'device-001',
  name: 'iPhone 15 Pro',
  model: 'A2848',
  brand: 'Apple',
  os: 'iOS',
  osVersion: '17.2',
  status: 'online',
  screenResolution: '2556x1179',
  screenSize: 6.1,
  cpu: 'A17 Pro',
  memory: '8GB',
  storage: '256GB',
  batteryLevel: 85,
  occupiedBy: undefined,
  occupiedAt: undefined,
  lastActiveAt: '2024-01-15 10:30:00',
  tags: ['iPhone', 'iOS17', '5G'],
}

export default function DeviceDetail() {
  const { id: _deviceId } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const statusConfig: Record<string, { color: string; text: string }> = {
    online: { color: 'green', text: '在线' },
    offline: { color: 'default', text: '离线' },
    busy: { color: 'orange', text: '占用中' },
    maintaining: { color: 'red', text: '维护中' },
  }

  const { color, text } = statusConfig[mockDevice.status] || { color: 'default', text: '未知' }

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/devices')}>
          返回列表
        </Button>
      </Space>

      <Title level={3}>{mockDevice.name}</Title>

      <Card>
        <Descriptions bordered column={2}>
          <Descriptions.Item label="设备ID">{mockDevice.id}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={color}>{text}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="品牌">{mockDevice.brand}</Descriptions.Item>
          <Descriptions.Item label="型号">{mockDevice.model}</Descriptions.Item>
          <Descriptions.Item label="操作系统">{mockDevice.os}</Descriptions.Item>
          <Descriptions.Item label="系统版本">{mockDevice.osVersion}</Descriptions.Item>
          <Descriptions.Item label="分辨率">{mockDevice.screenResolution}</Descriptions.Item>
          <Descriptions.Item label="屏幕尺寸">{mockDevice.screenSize}英寸</Descriptions.Item>
          <Descriptions.Item label="CPU">{mockDevice.cpu}</Descriptions.Item>
          <Descriptions.Item label="内存">{mockDevice.memory}</Descriptions.Item>
          <Descriptions.Item label="存储">{mockDevice.storage}</Descriptions.Item>
          <Descriptions.Item label="电量">{mockDevice.batteryLevel}%</Descriptions.Item>
          <Descriptions.Item label="最后活跃">{mockDevice.lastActiveAt}</Descriptions.Item>
          <Descriptions.Item label="标签">
            {mockDevice.tags.map((tag: string) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </Descriptions.Item>
        </Descriptions>

        <Space style={{ marginTop: 24 }}>
          <Button type="primary" icon={<PlayCircleOutlined />}>
            开始投屏
          </Button>
          {mockDevice.status === 'online' ? (
            <Button icon={<LockOutlined />}>占用设备</Button>
          ) : mockDevice.status === 'busy' ? (
            <Button icon={<UnlockOutlined />}>释放设备</Button>
          ) : null}
        </Space>
      </Card>

      <Card title="操作历史" style={{ marginTop: 16 }}>
        <Timeline
          items={[
            { children: '用户张三 占用了设备 - 2024-01-15 09:00:00' },
            { children: '执行了测试脚本 login_test.py - 2024-01-15 09:30:00' },
            { children: '用户张三 释放了设备 - 2024-01-15 10:00:00' },
            { children: '设备状态更新为在线 - 2024-01-15 10:30:00' },
          ]}
        />
      </Card>
    </div>
  )
}
