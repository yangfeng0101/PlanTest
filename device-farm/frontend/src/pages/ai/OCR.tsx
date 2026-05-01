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
} from 'antd'
import UploadOutlined from '@ant-design/icons/UploadOutlined'
import ScanOutlined from '@ant-design/icons/ScanOutlined'
import CopyOutlined from '@ant-design/icons/CopyOutlined'
import FileImageOutlined from '@ant-design/icons/FileImageOutlined'
import type { UploadFile } from 'antd/es/upload/interface'
import { useAuthenticatedFetch } from '@/stores'

const { TextArea } = Input
const { Title, Text, Paragraph } = Typography

interface TextRegion {
  text: string
  confidence: number
  bbox: number[][]
  center: number[]
}

interface OCRResult {
  text: string
  regions: TextRegion[]
  language: string
  processing_time_ms: number
}

const AI_OCR_SERVICE_URL = '/api/v1/ocr'

export default function OCRPage() {
  const fetchWithAuth = useAuthenticatedFetch()
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [imagePreview, setImagePreview] = useState<string>('')
  const [imageBase64, setImageBase64] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<OCRResult | null>(null)
  const [searchText, setSearchText] = useState('')
  const [findResult, setFindResult] = useState<TextRegion[] | null>(null)

  // Handle file upload
  const handleUpload = useCallback((file: File) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const base64 = e.target?.result as string
      setImagePreview(base64)
      setImageBase64(base64.split(',')[1]) // Remove data URL prefix
      setResult(null)
      setFindResult(null)
    }
    reader.readAsDataURL(file)
    return false // Prevent default upload behavior
  }, [])

  // Perform OCR recognition
  const handleRecognize = async () => {
    if (!imageBase64) {
      message.warning('请先上传图片')
      return
    }

    setLoading(true)
    try {
      const response = await fetchWithAuth(`${AI_OCR_SERVICE_URL}/recognize`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          image_base64: imageBase64,
        }),
      })

      if (!response.ok) {
        throw new Error('OCR recognition failed')
      }

      const data = await response.json()
      setResult(data)
      message.success(`识别完成，耗时 ${data.processing_time_ms.toFixed(2)}ms`)
    } catch (error) {
      message.error('OCR识别失败: ' + (error as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // Find specific text
  const handleFindText = async () => {
    if (!imageBase64) {
      message.warning('请先上传图片')
      return
    }
    if (!searchText.trim()) {
      message.warning('请输入要查找的文字')
      return
    }

    setLoading(true)
    try {
      const response = await fetchWithAuth(`${AI_OCR_SERVICE_URL}/find`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          image_base64: imageBase64,
          search_text: searchText,
          threshold: 0.8,
        }),
      })

      if (!response.ok) {
        throw new Error('Find text failed')
      }

      const data = await response.json()
      setFindResult(data.matches)
      if (data.found) {
        message.success(`找到 ${data.matches.length} 处匹配`)
      } else {
        message.info('未找到匹配文字')
      }
    } catch (error) {
      message.error('查找文字失败: ' + (error as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // Copy text to clipboard
  const handleCopyText = () => {
    if (result?.text) {
      navigator.clipboard.writeText(result.text)
      message.success('已复制到剪贴板')
    }
  }

  // Table columns for regions
  const columns = [
    {
      title: '文字内容',
      dataIndex: 'text',
      key: 'text',
      width: '40%',
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      key: 'confidence',
      width: '15%',
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
      width: '20%',
      render: (center: number[]) => `(${center[0]}, ${center[1]})`,
    },
    {
      title: '边界框',
      dataIndex: 'bbox',
      key: 'bbox',
      width: '25%',
      render: (bbox: number[][]) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          [{bbox.map(p => `(${p[0]},${p[1]})`).join(', ')}]
        </Text>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>
        <FileImageOutlined /> OCR 文字识别
      </Title>
      <Paragraph type="secondary">
        上传截图或图片，自动识别其中的文字内容，支持中英文识别
      </Paragraph>

      <Divider />

      <div style={{ display: 'flex', gap: 24 }}>
        {/* Left: Upload and Preview */}
        <Card title="图片上传" style={{ flex: 1 }}>
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
                setFindResult(null)
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

            <Space>
              <Button
                type="primary"
                icon={<ScanOutlined />}
                onClick={handleRecognize}
                loading={loading}
                disabled={!imageBase64}
              >
                开始识别
              </Button>
            </Space>
          </Space>
        </Card>

        {/* Right: Results */}
        <Card title="识别结果" style={{ flex: 1 }}>
          <Spin spinning={loading}>
            {result ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                <div>
                  <Space>
                    <Text strong>识别文字：</Text>
                    <Tag color="blue">{result.language}</Tag>
                    <Text type="secondary">
                      耗时 {result.processing_time_ms.toFixed(2)}ms
                    </Text>
                  </Space>
                  <div style={{ marginTop: 8 }}>
                    <TextArea
                      value={result.text}
                      autoSize={{ minRows: 3, maxRows: 10 }}
                      readOnly
                    />
                    <Button
                      icon={<CopyOutlined />}
                      onClick={handleCopyText}
                      style={{ marginTop: 8 }}
                    >
                      复制文字
                    </Button>
                  </div>
                </div>

                <Divider />

                <div>
                  <Text strong>文字区域详情 ({result.regions.length} 个区域)</Text>
                  <Table
                    dataSource={result.regions}
                    columns={columns}
                    rowKey={(_, index) => `region-${index}`}
                    size="small"
                    pagination={{ pageSize: 10 }}
                    style={{ marginTop: 8 }}
                  />
                </div>
              </Space>
            ) : (
              <Text type="secondary">请上传图片并点击"开始识别"</Text>
            )}
          </Spin>
        </Card>
      </div>

      <Divider />

      {/* Find Text Section */}
      <Card title="查找文字">
        <Space.Compact style={{ width: '100%', maxWidth: 600 }}>
          <Input
            placeholder="输入要查找的文字"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onPressEnter={handleFindText}
          />
          <Button type="primary" onClick={handleFindText} loading={loading}>
            查找
          </Button>
        </Space.Compact>

        {findResult && (
          <div style={{ marginTop: 16 }}>
            <Text>
              找到 <Text strong>{findResult.length}</Text> 处匹配
            </Text>
            {findResult.length > 0 && (
              <Table
                dataSource={findResult}
                columns={columns.slice(0, 3)}
                rowKey={(_, index) => `find-${index}`}
                size="small"
                pagination={false}
                style={{ marginTop: 8 }}
              />
            )}
          </div>
        )}
      </Card>
    </div>
  )
}
