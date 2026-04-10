import { useEffect, useState } from 'react'
import { Card, Table, Tag, Button, Space, Progress, Modal, Descriptions, Timeline, Tabs, Statistic, Row, Col, DatePicker, Select, Badge } from 'antd'
import {
  FileTextOutlined,
  DownloadOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import type { Report } from '@/types'

const { RangePicker } = DatePicker
const { Option } = Select

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([])
  const [loading, setLoading] = useState(false)
  const [detailVisible, setDetailVisible] = useState(false)
  const [currentReport, setCurrentReport] = useState<Report | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null)

  useEffect(() => {
    fetchReports()
  }, [])

  const fetchReports = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/v1/reports')
      const data = await response.json()
      setReports(data.data || data || [])
    } catch (error) {
      console.error('Failed to fetch reports:', error)
      // 使用模拟数据
      setReports([
        {
          id: '1',
          taskId: 'task-001',
          deviceName: 'iPhone 15 Pro',
          scriptName: '登录流程测试',
          status: 'success',
          summary: { total: 10, passed: 10, failed: 0, skipped: 0 },
          duration: 120,
          createdAt: '2024-01-15 10:30:00',
          logs: '测试执行完成，所有用例通过',
          screenshots: [],
        },
        {
          id: '2',
          taskId: 'task-002',
          deviceName: 'Samsung Galaxy S24',
          scriptName: '支付流程测试',
          status: 'failed',
          summary: { total: 8, passed: 6, failed: 2, skipped: 0 },
          duration: 180,
          createdAt: '2024-01-15 11:00:00',
          logs: '部分测试用例执行失败',
          screenshots: [],
        },
        {
          id: '3',
          taskId: 'task-003',
          deviceName: 'Huawei Mate 60',
          scriptName: '搜索功能测试',
          status: 'success',
          summary: { total: 15, passed: 15, failed: 0, skipped: 0 },
          duration: 90,
          createdAt: '2024-01-15 12:00:00',
          logs: '测试执行完成',
          screenshots: [],
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleViewDetail = (report: Report) => {
    setCurrentReport(report)
    setDetailVisible(true)
  }

  const handleDownload = (report: Report) => {
    // 下载报告
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report-${report.id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const filteredReports = reports.filter((report) => {
    const matchStatus = statusFilter === 'all' || report.status === statusFilter
    const matchDate = !dateRange || !dateRange[0] || !dateRange[1] || (
      dayjs(report.createdAt).isAfter(dateRange[0]) &&
      dayjs(report.createdAt).isBefore(dateRange[1].add(1, 'day'))
    )
    return matchStatus && matchDate
  })

  const totalTests = reports.reduce((sum, r) => sum + r.summary.total, 0)
  const totalPassed = reports.reduce((sum, r) => sum + r.summary.passed, 0)
  const totalFailed = reports.reduce((sum, r) => sum + r.summary.failed, 0)
  const successRate = totalTests > 0 ? ((totalPassed / totalTests) * 100).toFixed(1) : '0'

  const columns = [
    {
      title: '报告ID',
      dataIndex: 'id',
      key: 'id',
      width: 100,
    },
    {
      title: '设备名称',
      dataIndex: 'deviceName',
      key: 'deviceName',
    },
    {
      title: '脚本名称',
      dataIndex: 'scriptName',
      key: 'scriptName',
    },
    {
      title: '执行状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'success' ? 'green' : 'red'}>
          {status === 'success' ? '成功' : '失败'}
        </Tag>
      ),
    },
    {
      title: '用例统计',
      key: 'summary',
      render: (_: unknown, record: Report) => (
        <Space>
          <Badge color="green" text={`通过: ${record.summary.passed}`} />
          <Badge color="red" text={`失败: ${record.summary.failed}`} />
          <Badge color="default" text={`跳过: ${record.summary.skipped}`} />
        </Space>
      ),
    },
    {
      title: '执行时长',
      dataIndex: 'duration',
      key: 'duration',
      render: (duration: number) => `${duration}s`,
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 180,
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_: unknown, record: Report) => (
        <Space>
          <Button type="link" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)}>
            查看
          </Button>
          <Button type="link" icon={<DownloadOutlined />} onClick={() => handleDownload(record)}>
            下载
          </Button>
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
                title="总测试数"
                value={totalTests}
                prefix={<FileTextOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="通过数"
                value={totalPassed}
                valueStyle={{ color: '#52c41a' }}
                prefix={<CheckCircleOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="失败数"
                value={totalFailed}
                valueStyle={{ color: '#ff4d4f' }}
                prefix={<CloseCircleOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="成功率"
                value={successRate}
                suffix="%"
                prefix={<ClockCircleOutlined />}
              />
            </Card>
          </Col>
        </Row>
      </div>

      <Card
        title="测试报告"
        extra={
          <Space>
            <RangePicker
              onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)}
              placeholder={['开始日期', '结束日期']}
            />
            <Select
              value={statusFilter}
              style={{ width: 120 }}
              onChange={setStatusFilter}
            >
              <Option value="all">全部状态</Option>
              <Option value="success">成功</Option>
              <Option value="failed">失败</Option>
            </Select>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={filteredReports}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal
        title="报告详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={null}
        width={800}
      >
        {currentReport && (
          <div>
            <Descriptions bordered column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="报告ID">{currentReport.id}</Descriptions.Item>
              <Descriptions.Item label="任务ID">{currentReport.taskId}</Descriptions.Item>
              <Descriptions.Item label="设备名称">{currentReport.deviceName}</Descriptions.Item>
              <Descriptions.Item label="脚本名称">{currentReport.scriptName}</Descriptions.Item>
              <Descriptions.Item label="执行状态">
                <Tag color={currentReport.status === 'success' ? 'green' : 'red'}>
                  {currentReport.status === 'success' ? '成功' : '失败'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="执行时长">{currentReport.duration}s</Descriptions.Item>
              <Descriptions.Item label="创建时间" span={2}>
                {currentReport.createdAt}
              </Descriptions.Item>
            </Descriptions>

            <Card title="测试统计" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col span={6}>
                  <Statistic title="总用例数" value={currentReport.summary.total} />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="通过数"
                    value={currentReport.summary.passed}
                    valueStyle={{ color: '#52c41a' }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="失败数"
                    value={currentReport.summary.failed}
                    valueStyle={{ color: '#ff4d4f' }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="通过率"
                    value={
                      currentReport.summary.total > 0
                        ? ((currentReport.summary.passed / currentReport.summary.total) * 100).toFixed(1)
                        : '0'
                    }
                    suffix="%"
                  />
                </Col>
              </Row>
              <Progress
                percent={
                  currentReport.summary.total > 0
                    ? (currentReport.summary.passed / currentReport.summary.total) * 100
                    : 0
                }
                status={currentReport.status === 'success' ? 'success' : 'exception'}
                style={{ marginTop: 16 }}
              />
            </Card>

            <Tabs
              items={[
                {
                  key: 'logs',
                  label: '执行日志',
                  children: (
                    <pre style={{
                      background: '#f5f5f5',
                      padding: 16,
                      borderRadius: 4,
                      maxHeight: 300,
                      overflow: 'auto',
                    }}>
                      {currentReport.logs}
                    </pre>
                  ),
                },
                {
                  key: 'timeline',
                  label: '执行时间线',
                  children: (
                    <Timeline
                      items={[
                        {
                          color: 'blue',
                          children: `开始执行 ${currentReport.createdAt}`,
                        },
                        {
                          color: currentReport.status === 'success' ? 'green' : 'red',
                          children: `执行完成 耗时 ${currentReport.duration}s`,
                        },
                      ]}
                    />
                  ),
                },
              ]}
            />
          </div>
        )}
      </Modal>
    </div>
  )
}
