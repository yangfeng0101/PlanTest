// TrendChart - Reusable chart component for trend visualization
import { useMemo } from 'react'
import { Card, Spin, Empty, Select, Space } from 'antd'
import {
  LineChartOutlined,
  BarChartOutlined,
  AreaChartOutlined,
  DotChartOutlined,
} from '@ant-design/icons'

const { Option } = Select

export interface DataPoint {
  timestamp: string
  value: number
}

export interface TrendChartProps {
  title: string
  data: DataPoint[]
  loading?: boolean
  height?: number
  showLegend?: boolean
  color?: string
  chartType?: 'line' | 'bar' | 'area' | 'histogram'
  yAxisLabel?: string
  xAxisLabel?: string
  onChartTypeChange?: (type: 'line' | 'bar' | 'area' | 'histogram') => void
}

export default function TrendChart({
  title,
  data,
  loading = false,
  height = 300,
  showLegend = true,
  color = '#1890ff',
  chartType = 'line',
  onChartTypeChange,
}: TrendChartProps) {
  // Calculate min/max for Y axis
  const { minValue, maxValue, avgValue } = useMemo(() => {
    if (!data || data.length === 0) {
      return { minValue: 0, maxValue: 100, avgValue: 0 }
    }

    const values = data.map(d => d.value)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const avg = values.reduce((a, b) => a + b, 0) / values.length

    return {
      minValue: Math.floor(min * 0.9),
      maxValue: Math.ceil(max * 1.1),
      avgValue: avg.toFixed(2),
    }
  }, [data])

  // Format date for display
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return `${date.getMonth() + 1}/${date.getDate()}`
  }

  // Render simple chart using CSS/SVG
  const renderChart = () => {
    if (!data || data.length === 0) {
      return <Empty description="暂无数据" />
    }

    const chartWidth = 100
    const chartHeight = 80
    const padding = 5
    const range = maxValue - minValue || 1

    // Generate path for line/area chart
    const points = data.map((d, i) => {
      const x = padding + (i / (data.length - 1 || 1)) * (chartWidth - padding * 2)
      const y = chartHeight - padding - ((d.value - minValue) / range) * (chartHeight - padding * 2)
      return { x, y, value: d.value, timestamp: d.timestamp }
    })

    const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
    const areaD = `${pathD} L ${points[points.length - 1].x} ${chartHeight - padding} L ${padding} ${chartHeight - padding} Z`

    // Calculate bar width for bar chart
    const barWidth = (chartWidth - padding * 2) / (data.length || 1) - 2

    return (
      <div style={{ position: 'relative' }}>
        {/* Y-axis labels */}
        <div style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: chartType === 'histogram' ? 20 : 30,
          width: chartType === 'histogram' ? 50 : 40,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          fontSize: 10,
          color: '#999',
        }}>
          <span>{chartType === 'histogram' ? maxValue.toFixed(0) : maxValue.toFixed(1)}</span>
          <span>{chartType === 'histogram' ? ((maxValue + minValue) / 2).toFixed(0) : ((maxValue + minValue) / 2).toFixed(1)}</span>
          <span>{chartType === 'histogram' ? minValue.toFixed(0) : minValue.toFixed(1)}</span>
        </div>

        {/* Chart area */}
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          style={{ width: 'calc(100% - 60px)', height: height - 50, marginLeft: chartType === 'histogram' ? 55 : 45 }}
          preserveAspectRatio="none"
        >
          {/* Grid lines */}
          <line x1={padding} y1={padding} x2={chartWidth - padding} y2={padding} stroke="#f0f0f0" strokeWidth="0.5" />
          <line x1={padding} y1={(chartHeight + padding) / 2} x2={chartWidth - padding} y2={(chartHeight + padding) / 2} stroke="#f0f0f0" strokeWidth="0.5" />
          <line x1={padding} y1={chartHeight - padding} x2={chartWidth - padding} y2={chartHeight - padding} stroke="#f0f0f0" strokeWidth="0.5" />

          {chartType === 'area' && (
            <path d={areaD} fill={`${color}20`} stroke="none" />
          )}

          {chartType === 'histogram' ? (
            <g>
              {points.map((p, i) => {
                // For histogram, show bars from the bottom
                const barHeight = chartHeight - padding - p.y
                return (
                  <rect
                    key={i}
                    x={padding + i * ((chartWidth - padding * 2) / (data.length || 1)) + 0.5}
                    y={p.y}
                    width={Math.max(1, barWidth)}
                    height={barHeight}
                    fill={color}
                    opacity={0.7}
                  />
                )
              })}
            </g>
          ) : chartType === 'bar' ? (
            <g>
              {points.map((p, i) => (
                <rect
                  key={i}
                  x={padding + i * ((chartWidth - padding * 2) / (data.length || 1))}
                  y={p.y}
                  width={Math.max(1, barWidth)}
                  height={chartHeight - padding - p.y}
                  fill={color}
                  opacity={0.8}
                />
              ))}
            </g>
          ) : (
            <path
              d={pathD}
              fill="none"
              stroke={color}
              strokeWidth="0.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Data points */}
          {chartType !== 'bar' && chartType !== 'histogram' && points.map((p, i) => (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r="1"
              fill={color}
            />
          ))}
        </svg>

        {/* X-axis labels */}
        <div style={{
          display: 'flex',
          justifyContent: chartType === 'histogram' ? 'center' : 'space-between',
          marginLeft: chartType === 'histogram' ? 55 : 45,
          paddingRight: 10,
          fontSize: 10,
          color: '#999',
          marginTop: 5,
        }}>
          {chartType === 'histogram' ? (
            <span>{data[0]?.timestamp || 'Range'}</span>
          ) : data.length > 0 && (
            <>
              <span>{formatDate(data[0].timestamp)}</span>
              {data.length > 2 && <span>{formatDate(data[Math.floor(data.length / 2)].timestamp)}</span>}
              <span>{formatDate(data[data.length - 1].timestamp)}</span>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <Card
      title={
        <Space>
          <span>{title}</span>
          {onChartTypeChange && (
            <Select
              value={chartType}
              onChange={onChartTypeChange}
              size="small"
              style={{ width: 80 }}
            >
              <Option value="line"><LineChartOutlined /> 折线</Option>
              <Option value="bar"><BarChartOutlined /> 柱状</Option>
              <Option value="area"><AreaChartOutlined /> 面积</Option>
              <Option value="histogram"><DotChartOutlined /> 分布</Option>
            </Select>
          )}
        </Space>
      }
      extra={
        showLegend && data && data.length > 0 && (
          <Space size="large">
            <span style={{ fontSize: 12, color: '#999' }}>平均: {avgValue}</span>
            <span style={{ fontSize: 12, color: '#52c41a' }}>最高: {maxValue.toFixed(2)}</span>
            <span style={{ fontSize: 12, color: '#ff4d4f' }}>最低: {minValue.toFixed(2)}</span>
          </Space>
        )
      }
    >
      <Spin spinning={loading}>
        <div style={{ minHeight: height }}>
          {renderChart()}
        </div>
      </Spin>
    </Card>
  )
}
