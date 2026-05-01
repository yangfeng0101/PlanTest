import { useState, useCallback } from 'react'
import {
  Card,
  Upload,
  Button,
  Input,
  message,
  Table,
  Tag,
  Space,
  Spin,
  Typography,
  Divider,
  Select,
} from 'antd'
import UploadOutlined from '@ant-design/icons/UploadOutlined'
import AimOutlined from '@ant-design/icons/AimOutlined'
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined'
import CloseCircleOutlined from '@ant-design/icons/CloseCircleOutlined'
import type { UploadFile } from 'antd/es/upload/interface'
import { useAuthenticatedFetch } from '@/stores'

const { TextArea } = Input
const { Title, Text, Paragraph } = Typography

interface LocatedElement {
  element_type: string
  description: string
  text: string | null
  confidence: number
  bbox: number[][]
  center: number[]
  clickable: boolean
  attributes: Record<string, unknown>
}

interface LocateResult {
  elements: LocatedElement[]
  query: string
  processing_time_ms: number
  found: boolean
}

const AI_LOCATE_SERVICE_URL = '/api/v1/locate'

export default function LocatePage() {
  const fetchWithAuth = useAuthenticatedFetch()
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [imagePreview, setImagePreview] = useState<string>('')
  const [imageBase64, setImageBase64] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [description, setDescription] = useState('')
  const [result, setResult] = useState<LocateResult | null>(null)
  const [elementType, setElementType] = useState<string | null>(null)

  // Handle file upload
  const handleUpload = useCallback((file: File) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const base64 = e.target?.result as string
      setImagePreview(base64)
      setImageBase64(base64.split(',')[1]) // Remove data URL prefix
      setResult(null)
    }
    reader.readAsDataURL(file)
    return false
  }, [])

  // Locate element
  const handleLocate = async () => {
    if (!imageBase64) {
      message.warning('请先上传图片')
      return
    }
    if (!description.trim()) {
      message.warning('请输入元素描述')
      return
    }

    setLoading(true)
    try {
      const response = await fetchWithAuth(`${AI_LOCATE_SERVICE_URL}/locate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          image_base64: imageBase64,
          description: description,
        }),
      })

      if (!response.ok) {
        throw new Error('Element location failed')
      }

      const data = await response.json()
      setResult(data)
      if (data.found) {
        message.success(`找到 ${data.elements.length} 个元素，耗时 ${data.processing_time_ms.toFixed(2)}ms`)
      } else {
        message.info('未找到匹配元素')
      }
    } catch (error) {
      message.error('元素定位失败: ' + (error as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // Table columns
  const columns = [
    {
      title: '元素类型',
      dataIndex: 'element_type',
      key: 'element_type',
      width: '12%',
      render: (type: string) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      width: '20%',
    },
    {
      title: '文字',
      dataIndex: 'text',
      key: 'text',
      width: '15%',
      render: (text: string | null) => text || '-',
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: '10%',
      render: (confidence: number) => (
        <Tag color={confidence > 0.9 ? 'green' : confidence > 0.7 ? 'orange' : 'red'}>
          {(confidence * 100).toFixed(1)}%
        </Tag>
      ),
    },
    {
      title: '中心坐标',
      dataIndex: 'center',
      key: 'center',
      width: '13%',
      render: (center: number[]) => `(${center[0]}, ${center[1]})`,
    },
    {
      title: '可点击',
      dataIndex: 'clickable',
      key: 'clickable',
      width: '10%',
      render: (clickable: boolean) =>
        clickable ? (
          <CheckCircleOutlined style={{ color: '#52c41a' }} />
        ) : (
          <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
        ),
    },
    {
      title: '边界框',
      dataIndex: 'bbox',
      key: 'bbox',
      width: '20%',
      render: (bbox: number[][]) => (
        <Text type="secondary" style={{ fontSize: 11 }}>
          [{bbox.map(p => `(${p[0]},${p[1]})`).join(', ')}]
        </Text>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>
        <AimOutlined /> 元素定位
      </Title>
      <Paragraph type="secondary">
        上传截图，使用自然语言描述要定位的UI元素，自动识别元素位置和属性
      </Paragraph>

      <Divider />

      <div style={{ display: 'flex', gap: 24 }}>
        {/* Left: Upload and Input */}
        <Card title="图片和描述" style={{ flex: 1 }}>
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Upload
              fileList={fileList}
              beforeUpload={handleUpload}
              onChange={({ fileList }) => setFileList(fileList)}
              accept="image/*"
              maxCount={1}
              onRemove={() => {
                setImagePreview('')
                setImageBase64('')
                setResult(null)
              }}
            >
              <Button icon={<UploadOutlined />}>选择图片</Button>
            </Upload>

            {imagePreview && (
              <div style={{ marginTop: 16 }}>
                <img
                  src={imagePreview}
                  alt="Preview"
                  style={{
                    maxWidth: '100%',
                    maxHeight: 400,
                    border: '1px solid #d9d9d9',
                    borderRadius: 4,
                  }}
                />
              </div>
            )}

            <Divider />

            <div>
              <Text strong>元素描述</Text>
              <TextArea
                placeholder="例如：登录按钮、用户名输入框、确定按钮、搜索框..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                autoSize={{ minRows: 2, maxRows: 4 }}
                style={{ marginTop: 8 }}
              />
            </div>

            <Space>
              <Select
                placeholder="筛选元素类型"
                value={elementType}
                onChange={setElementType}
                allowClear
                style={{ width: 150 }}
                options={[
                  { label: '按钮', value: 'button' },
                  { label: '输入框', value: 'input' },
                  { label: '文本', value: 'text' },
                  { label: '图标', value: 'icon' },
                  { label: '图片', value: 'image' },
                ]}
              />
              <Button
                type="primary"
                icon={<AimOutlined />}
                onClick={handleLocate}
                loading={loading}
                disabled={!imageBase64 || !description}
              >
                定位元素
              </Button>
            </Space>
          </Space>
        </Card>

        {/* Right: Results */}
        <Card title="定位结果" style={{ flex: 1 }}>
          <Spin spinning={loading}>
            {result ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                <Space>
                  <Text strong>查询：</Text>
                  <Text code>{result.query}</Text>
                  <Tag color={result.found ? 'green' : 'red'}>
                    {result.found ? '已找到' : '未找到'}
                  </Tag>
                  <Text type="secondary">
                    耗时 {result.processing_time_ms.toFixed(2)}ms
                  </Text>
                </Space>

                {result.found && (
                  <>
                    <Divider />
                    <Text strong>
                      找到 {result.elements.length} 个元素
                    </Text>
                    <Table
                      dataSource={
                        elementType
                          ? result.elements.filter((e) => e.element_type === elementType)
                          : result.elements
                      }
                      columns={columns}
                      rowKey={(_, index) => `element-${index}`}
                      size="small"
                      pagination={{ pageSize: 10 }}
                      scroll={{ x: 800 }}
                    />
                  </>
                )}
              </Space>
            ) : (
              <Text type="secondary">请上传图片并输入元素描述</Text>
            )}
          </Spin>
        </Card>
      </div>
    </div>
  )
}
