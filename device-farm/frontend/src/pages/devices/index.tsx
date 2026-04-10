import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Row, Col, Tag, Button, Input, Select, Space, Switch, Table, Statistic, Badge, message } from 'antd'
import {
  MobileOutlined,
  SearchOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons'
import DeviceCard from '@/components/DeviceCard'
import { useDeviceStore } from '@/stores/deviceStore'
import type { Device } from '@/types'

const { Search } = Input
const { Option } = Select

export default function DevicesPage() {
  const navigate = useNavigate()
  const { devices, loading, viewMode, fetchDevices, setViewMode, occupyDevice, releaseDevice } = useDeviceStore()
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  useEffect(() => {
    fetchDevices()
  }, [fetchDevices])

  const filteredDevices = devices.filter((device) => {
    const matchKeyword = !keyword ||
      device.name.includes(keyword) ||
      device.model.includes(keyword) ||
      device.brand.includes(keyword)
    const matchStatus = statusFilter === 'all' || device.status === statusFilter
    return matchKeyword && matchStatus
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
    navigate(`/screen?deviceId=${id}`)
  }

  const onlineCount = devices.filter((d) => d.status === 'online').length
  const busyCount = devices.filter((d) => d.status === 'busy').length
  const offlineCount = devices.filter((d) => d.status === 'offline').length

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
      title: '电量',
      dataIndex: 'batteryLevel',
      key: 'batteryLevel',
      render: (level: number) => `${level}%`,
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

      <Card>
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
          <Space>
            <Search
              placeholder="搜索设备名称/型号/品牌"
              allowClear
              style={{ width: 300 }}
              onSearch={setKeyword}
              prefix={<SearchOutlined />}
            />
            <Select
              value={statusFilter}
              style={{ width: 150 }}
              onChange={setStatusFilter}
            >
              <Option value="all">全部状态</Option>
              <Option value="online">在线</Option>
              <Option value="busy">占用中</Option>
              <Option value="offline">离线</Option>
              <Option value="maintaining">维护中</Option>
            </Select>
          </Space>
          <Space>
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
