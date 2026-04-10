import { useState, useEffect } from 'react'
import { Row, Col, Card, DatePicker, Select, Space, Statistic, Spin, Typography, Progress } from 'antd'
import {
  MobileOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  RiseOutlined,
} from '@ant-design/icons'
import dayjs, { Dayjs } from 'dayjs'
import TrendChart from '@/components/TrendChart'
import type { DataPoint } from '@/components/TrendChart'
import './Trend.css'

const { Title } = Typography
const { RangePicker } = DatePicker

interface StatisticsSummary {
  totalDeviceHours: number
  totalTasks: number
  successRate: number
  avgSessionMinutes: number
}

interface TopDevice {
  device_id: string
  device_name: string
  usage_hours: number
}

interface TopUser {
  user_id: string
  usage_hours: number
}

interface ResponseTimeBucket {
  label: string
  count: number
  percentage: number
}

export default function TrendPage() {
  const [loading, setLoading] = useState(false)
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(7, 'days'),
    dayjs(),
  ])
  const [granularity, setGranularity] = useState<'hourly' | 'daily' | 'weekly' | 'monthly'>('daily')
  const [chartType, setChartType] = useState<'line' | 'bar' | 'area' | 'histogram'>('line')

  // Statistics data
  const [summary, setSummary] = useState<StatisticsSummary>({
    totalDeviceHours: 0,
    totalTasks: 0,
    successRate: 0,
    avgSessionMinutes: 0,
  })
  const [deviceUsageData, setDeviceUsageData] = useState<DataPoint[]>([])
  const [taskCountData, setTaskCountData] = useState<DataPoint[]>([])
  const [successRateData, setSuccessRateData] = useState<DataPoint[]>([])
  const [responseTimeDistribution, setResponseTimeDistribution] = useState<ResponseTimeBucket[]>([])
  const [topDevices, setTopDevices] = useState<TopDevice[]>([])
  const [topUsers, setTopUsers] = useState<TopUser[]>([])

  // Fetch statistics data
  const fetchStatistics = async () => {
    setLoading(true)
    try {
      // Fetch device usage trend
      const trendParams = new URLSearchParams({
        metric: 'device_hours',
        granularity: granularity,
        start_time: dateRange[0].toISOString(),
        end_time: dateRange[1].toISOString(),
      })
      const trendRes = await fetch(`/api/v1/statistics/trend?${trendParams}`)
      if (trendRes.ok) {
        const trendData = await trendRes.json()
        setDeviceUsageData(trendData.data || [])
      }

      // Fetch task count trend
      const taskParams = new URLSearchParams({
        metric: 'task_count',
        granularity: granularity,
        start_time: dateRange[0].toISOString(),
        end_time: dateRange[1].toISOString(),
      })
      const taskRes = await fetch(`/api/v1/statistics/trend?${taskParams}`)
      if (taskRes.ok) {
        const taskData = await taskRes.json()
        setTaskCountData(taskData.data || [])
      }

      // Fetch success rate trend
      const successParams = new URLSearchParams({
        metric: 'success_rate',
        granularity: granularity,
        start_time: dateRange[0].toISOString(),
        end_time: dateRange[1].toISOString(),
      })
      const successRes = await fetch(`/api/v1/statistics/trend?${successParams}`)
      if (successRes.ok) {
        const successData = await successRes.json()
        setSuccessRateData(successData.data || [])
      }

      // Fetch response time distribution
      const responseTimeParams = new URLSearchParams({
        start_time: dateRange[0].toISOString(),
        end_time: dateRange[1].toISOString(),
      })
      const responseTimeRes = await fetch(`/api/v1/statistics/response-time-distribution?${responseTimeParams}`)
      if (responseTimeRes.ok) {
        const responseTimeData = await responseTimeRes.json()
        setResponseTimeDistribution(responseTimeData.distribution || [])
      }

      // Fetch weekly report for summary
      const reportRes = await fetch('/api/v1/statistics/reports/weekly')
      if (reportRes.ok) {
        const report = await reportRes.json()
        setSummary({
          totalDeviceHours: report.total_device_hours || 0,
          totalTasks: report.task_stats?.total_tasks || 0,
          successRate: report.task_stats?.success_rate || 0,
          avgSessionMinutes: report.device_usage?.[0]?.average_session_minutes || 0,
        })
        setTopDevices(report.top_devices || [])
        setTopUsers(report.top_users || [])
      }
    } catch (error) {
      console.error('Failed to fetch statistics:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatistics()
  }, [dateRange, granularity])

  const handleDateRangeChange = (dates: [Dayjs | null, Dayjs | null] | null) => {
    if (dates && dates[0] && dates[1]) {
      setDateRange([dates[0], dates[1]])
    }
  }

  const granularityOptions = [
    { label: '按小时', value: 'hourly' },
    { label: '按天', value: 'daily' },
    { label: '按周', value: 'weekly' },
    { label: '按月', value: 'monthly' },
  ]

  // Colors for response time distribution
  const responseTimeColors = [
    '#52c41a', // green - fast
    '#73d13d',
    '#faad14', // yellow - medium
    '#fa8c16',
    '#ff4d4f', // red - slow
    '#ff7875',
  ]

  return (
    <div className="trend-page">
      <div className="trend-header">
        <Title level={4}>趋势分析</Title>
        <Space>
          <RangePicker
            value={dateRange}
            onChange={handleDateRangeChange}
            allowClear={false}
          />
          <Select
            value={granularity}
            onChange={setGranularity}
            options={granularityOptions}
            style={{ width: 100 }}
          />
        </Space>
      </div>

      <Spin spinning={loading}>
        {/* Summary Statistics */}
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={6}>
            <Card>
              <Statistic
                title="设备使用总时长"
                value={summary.totalDeviceHours}
                suffix="小时"
                prefix={<MobileOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="任务执行总数"
                value={summary.totalTasks}
                prefix={<CheckCircleOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="任务成功率"
                value={summary.successRate}
                suffix="%"
                prefix={<RiseOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="平均会话时长"
                value={summary.avgSessionMinutes}
                suffix="分钟"
                prefix={<ClockCircleOutlined />}
              />
            </Card>
          </Col>
        </Row>

        {/* Trend Charts - Row 1 */}
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={12}>
            <TrendChart
              title="设备使用时长趋势"
              data={deviceUsageData}
              height={300}
              chartType={chartType}
              onChartTypeChange={setChartType}
              color="#1890ff"
              yAxisLabel="小时"
            />
          </Col>
          <Col span={12}>
            <TrendChart
              title="任务执行数量趋势"
              data={taskCountData}
              height={300}
              chartType={chartType}
              color="#52c41a"
              yAxisLabel="任务数"
            />
          </Col>
        </Row>

        {/* Trend Charts - Row 2 */}
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={12}>
            <TrendChart
              title="任务成功率趋势"
              data={successRateData}
              height={300}
              chartType={chartType}
              color="#722ed1"
              yAxisLabel="成功率(%)"
            />
          </Col>
          <Col span={12}>
            <Card title="响应时间分布" className="top-list-card">
              {responseTimeDistribution.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#999', padding: 20 }}>
                  暂无数据
                </div>
              ) : (
                <div style={{ padding: '10px 0' }}>
                  {responseTimeDistribution.map((bucket, index) => (
                    <div key={bucket.label} style={{ marginBottom: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span style={{ fontSize: 13 }}>{bucket.label}</span>
                        <span style={{ fontSize: 12, color: '#666' }}>
                          {bucket.count} 次 ({bucket.percentage}%)
                        </span>
                      </div>
                      <Progress
                        percent={bucket.percentage}
                        strokeColor={responseTimeColors[index]}
                        showInfo={false}
                        size="small"
                      />
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </Col>
        </Row>

        {/* Top Devices and Users */}
        <Row gutter={16}>
          <Col span={12}>
            <Card title="设备使用排行" className="top-list-card">
              {topDevices.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#999', padding: 20 }}>
                  暂无数据
                </div>
              ) : (
                <div className="top-list">
                  {topDevices.map((device, index) => (
                    <div key={device.device_id} className="top-list-item">
                      <span className="rank">#{index + 1}</span>
                      <span className="name">{device.device_name}</span>
                      <span className="value">{device.usage_hours.toFixed(1)} 小时</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </Col>
          <Col span={12}>
            <Card title="用户使用排行" className="top-list-card">
              {topUsers.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#999', padding: 20 }}>
                  暂无数据
                </div>
              ) : (
                <div className="top-list">
                  {topUsers.map((user, index) => (
                    <div key={user.user_id} className="top-list-item">
                      <span className="rank">#{index + 1}</span>
                      <span className="name">{user.user_id}</span>
                      <span className="value">{user.usage_hours.toFixed(1)} 小时</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  )
}
