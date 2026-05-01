import { useEffect, useState } from 'react'
import { Card, Table, Tag, Button, Space, Progress, Modal, Descriptions, Timeline, Tabs, Statistic, Row, Col, DatePicker, Select, Badge } from 'antd'
import FileTextOutlined from '@ant-design/icons/FileTextOutlined'
import DownloadOutlined from '@ant-design/icons/DownloadOutlined'
import EyeOutlined from '@ant-design/icons/EyeOutlined'
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined'
import CloseCircleOutlined from '@ant-design/icons/CloseCircleOutlined'
import ClockCircleOutlined from '@ant-design/icons/ClockCircleOutlined'
import LineChartOutlined from '@ant-design/icons/LineChartOutlined'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import type { Report } from '@/types'

const { RangePicker } = DatePicker
const { Option } = Select

export default function ReportsPage() {
  const navigate = useNavigate()
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
      setReports(data.items || data.data || data || [])
    } catch (error) {
      console.error('Failed to fetch reports:', error)
      // 使用模拟数据
      const fallbackReports: Report[] = [
        {
          id: '1',
          task_id: 'task-001',
          status: 'completed',
          format: 'json',
          detail: { summary: { total: 10, passed: 10, failed: 0, skipped: 0, duration: 120, success_rate: 100 } },
          created_at: '2024-01-15 10:30:00',
          updated_at: '2024-01-15 10:30:00',
        },
        {
          id: '2',
          task_id: 'task-002',
          status: 'failed',
          format: 'json',
          detail: { summary: { total: 8, passed: 6, failed: 2, skipped: 0, duration: 180, success_rate: 75 } },
          created_at: '2024-01-15 11:00:00',
          updated_at: '2024-01-15 11:00:00',
        },
        {
          id: '3',
          task_id: 'task-003',
          status: 'completed',
          format: 'json',
          detail: { summary: { total: 15, passed: 15, failed: 0, skipped: 0, duration: 90, success_rate: 100 } },
          created_at: '2024-01-15 12:00:00',
          updated_at: '2024-01-15 12:00:00',
        },
      ]
      setReports(fallbackReports)
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
      dayjs(report.created_at).isAfter(dateRange[0]) &&
      dayjs(report.created_at).isBefore(dateRange[1].add(1, 'day'))
    )
    return matchStatus && matchDate
  })

  const totalTests = reports.reduce((sum, r) => sum + (r.detail?.summary?.total || 0), 0)
  const totalPassed = reports.reduce((sum, r) => sum + (r.detail?.summary?.passed || 0), 0)
  const totalFailed = reports.reduce((sum, r) => sum + (r.detail?.summary?.failed || 0), 0)
  const successRate = totalTests > 0 ? ((totalPassed / totalTests) * 100).toFixed(1) : '0'

  const columns = [
    {
      title: '报告ID',
      dataIndex: 'id',
      key: 'id',
      width: 100,
    },
    {
      title: '任务ID',
      dataIndex: 'task_id',
      key: 'task_id',
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (title: string) => title || '-',
    },
    {
      title: '执行状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'completed' ? 'green' : status === 'failed' ? 'red' : 'blue'}>
          {status === 'completed' ? '成功' : status === 'failed' ? '失败' : status}
        </Tag>
      ),
    },
    {
      title: '用例统计',
      key: 'summary',
      render: (_: unknown, record: Report) => (
        <Space>
          <Badge color="green" text={`通过: ${record.detail?.summary?.passed || 0}`} />
          <Badge color="red" text={`失败: ${record.detail?.summary?.failed || 0}`} />
          <Badge color="default" text={`跳过: ${record.detail?.summary?.skipped || 0}`} />
        </Space>
      ),
    },
    {
      title: '执行时长',
      key: 'duration',
      render: (_: unknown, record: Report) => `${record.detail?.summary?.duration || 0}s`,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
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
            <Button
              type="primary"
              icon={<LineChartOutlined />}
              onClick={() => navigate('/reports/trend')}
            >
              趋势分析
            </Button>
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
              <Descriptions.Item label="任务ID">{currentReport.task_id}</Descriptions.Item>
              <Descriptions.Item label="格式">{currentReport.format}</Descriptions.Item>
              <Descriptions.Item label="执行状态">
                <Tag color={currentReport.status === 'completed' ? 'green' : currentReport.status === 'failed' ? 'red' : 'blue'}>
                  {currentReport.status === 'completed' ? '成功' : currentReport.status === 'failed' ? '失败' : currentReport.status}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="执行时长">{currentReport.detail?.summary?.duration || 0}s</Descriptions.Item>
              <Descriptions.Item label="创建时间" span={2}>
                {currentReport.created_at}
              </Descriptions.Item>
            </Descriptions>

            <Card title="测试统计" style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                <Col span={6}>
                  <Statistic title="总用例数" value={currentReport.detail?.summary?.total || 0} />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="通过数"
                    value={currentReport.detail?.summary?.passed || 0}
                    valueStyle={{ color: '#52c41a' }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="失败数"
                    value={currentReport.detail?.summary?.failed || 0}
                    valueStyle={{ color: '#ff4d4f' }}
                  />
                </Col>
                <Col span={6}>
                  <Statistic
                    title="通过率"
                    value={
                      (currentReport.detail?.summary?.total || 0) > 0
                        ? (((currentReport.detail?.summary?.passed || 0) / (currentReport.detail?.summary?.total || 1)) * 100).toFixed(1)
                        : '0'
                    }
                    suffix="%"
                  />
                </Col>
              </Row>
              <Progress
                percent={
                  (currentReport.detail?.summary?.total || 0) > 0
                    ? ((currentReport.detail?.summary?.passed || 0) / (currentReport.detail?.summary?.total || 1)) * 100
                    : 0
                }
                status={currentReport.status === 'completed' ? 'success' : 'exception'}
                style={{ marginTop: 16 }}
              />
            </Card>

            <Tabs
              items={[
                {
                  key: 'timeline',
                  label: '执行时间线',
                  children: (
                    <Timeline
                      items={[
                        {
                          color: 'blue',
                          children: `开始执行 ${currentReport.created_at}`,
                        },
                        {
                          color: currentReport.status === 'completed' ? 'green' : 'red',
                          children: `执行完成 耗时 ${currentReport.detail?.summary?.duration || 0}s`,
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
