import { useState } from 'react'
import {
  Card,
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
  Collapse,
  List,
  Alert,
} from 'antd'
import {
  CodeOutlined,
  ThunderboltOutlined,
  DownloadOutlined,
  BulbOutlined,
} from '@ant-design/icons'
import { useAuthenticatedFetch } from '@/stores'

const { TextArea } = Input
const { Title, Text, Paragraph } = Typography

interface TestStep {
  step_type: string
  description: string
  action: string
  target: string | null
  value: string | null
  timeout: number | null
}

interface TestCase {
  id: string
  name: string
  description: string
  test_type: string
  steps: TestStep[]
  preconditions: string[]
  postconditions: string[]
  tags: string[]
  priority: number
}

interface Template {
  id: string
  name: string
  description: string
  test_type: string
}

interface Suggestion {
  type: string
  message: string
  severity: string
  step_index: number | null
}

const AI_GENERATE_SERVICE_URL = '/api/v1/generate'

export default function GeneratePage() {
  const fetchWithAuth = useAuthenticatedFetch()
  const [loading, setLoading] = useState(false)
  const [description, setDescription] = useState('')
  const [testType, setTestType] = useState('functional_test')
  const [testName, setTestName] = useState('')
  const [result, setResult] = useState<TestCase | null>(null)
  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null)
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [exportFormat, setExportFormat] = useState('python')
  const [exportedScript, setExportedScript] = useState<string | null>(null)

  // Generate test case from description
  const handleGenerate = async () => {
    if (!description.trim()) {
      message.warning('请输入测试场景描述')
      return
    }

    setLoading(true)
    try {
      const response = await fetchWithAuth(`${AI_GENERATE_SERVICE_URL}/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          description: description,
          test_type: testType,
          test_name: testName || undefined,
        }),
      })

      if (!response.ok) {
        throw new Error('Test generation failed')
      }

      const data = await response.json()
      setResult(data)
      setSuggestions([])
      setExportedScript(null)
      message.success('测试用例生成成功')
    } catch (error) {
      message.error('生成失败: ' + (error as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // Load templates
  const handleLoadTemplates = async () => {
    try {
      const response = await fetchWithAuth(`${AI_GENERATE_SERVICE_URL}/templates`)
      if (!response.ok) {
        throw new Error('Failed to load templates')
      }
      const data = await response.json()
      setTemplates(data)
    } catch {
      message.error('加载模板失败')
    }
  }

  // Generate from template
  const handleGenerateFromTemplate = async () => {
    if (!selectedTemplate) {
      message.warning('请选择模板')
      return
    }

    setLoading(true)
    try {
      const response = await fetchWithAuth(`${AI_GENERATE_SERVICE_URL}/generate/from-template`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          template_id: selectedTemplate,
          test_name: testName || undefined,
        }),
      })

      if (!response.ok) {
        throw new Error('Template generation failed')
      }

      const data = await response.json()
      setResult(data)
      setSuggestions([])
      setExportedScript(null)
      message.success('测试用例生成成功')
    } catch (error) {
      message.error('生成失败: ' + (error as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // Get improvement suggestions
  const handleGetSuggestions = async () => {
    if (!result) {
      return
    }

    setLoading(true)
    try {
      const response = await fetchWithAuth(`${AI_GENERATE_SERVICE_URL}/suggest`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(result),
      })

      if (!response.ok) {
        throw new Error('Failed to get suggestions')
      }

      const data = await response.json()
      setSuggestions(data)
      message.success(`获得 ${data.length} 条改进建议`)
    } catch {
      message.error('获取建议失败')
    } finally {
      setLoading(false)
    }
  }

  // Export test case
  const handleExport = async () => {
    if (!result) {
      return
    }

    setLoading(true)
    try {
      const response = await fetchWithAuth(`${AI_GENERATE_SERVICE_URL}/export?format=${exportFormat}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(result),
      })

      if (!response.ok) {
        throw new Error('Export failed')
      }

      const data = await response.json()
      setExportedScript(data.script)
      message.success('导出成功')
    } catch {
      message.error('导出失败')
    } finally {
      setLoading(false)
    }
  }

  // Step columns
  const stepColumns = [
    {
      title: '序号',
      key: 'index',
      width: 60,
      render: (_: unknown, __: unknown, index: number) => index + 1,
    },
    {
      title: '类型',
      dataIndex: 'step_type',
      key: 'step_type',
      width: 100,
      render: (type: string) => <Tag color="blue">{type}</Tag>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      width: 200,
    },
    {
      title: '动作',
      dataIndex: 'action',
      key: 'action',
      width: 100,
      render: (action: string) => <Tag color="green">{action}</Tag>,
    },
    {
      title: '目标',
      dataIndex: 'target',
      key: 'target',
      width: 150,
      render: (target: string | null) => target || '-',
    },
    {
      title: '值',
      dataIndex: 'value',
      key: 'value',
      width: 150,
      render: (value: string | null) => value || '-',
    },
    {
      title: '超时',
      dataIndex: 'timeout',
      key: 'timeout',
      width: 80,
      render: (timeout: number | null) => (timeout ? `${timeout}s` : '-'),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>
        <CodeOutlined /> 用例生成
      </Title>
      <Paragraph type="secondary">
        使用自然语言描述测试场景，自动生成可执行的测试用例
      </Paragraph>

      <Divider />

      <div style={{ display: 'flex', gap: 24 }}>
        {/* Left: Input */}
        <Card title="测试场景描述" style={{ flex: 1 }}>
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <div>
              <Text strong>测试类型</Text>
              <Select
                value={testType}
                onChange={setTestType}
                style={{ width: '100%', marginTop: 8 }}
                options={[
                  { label: '功能测试', value: 'functional_test' },
                  { label: 'UI测试', value: 'ui_test' },
                  { label: '回归测试', value: 'regression_test' },
                  { label: '冒烟测试', value: 'smoke_test' },
                  { label: '性能测试', value: 'performance_test' },
                ]}
              />
            </div>

            <div>
              <Text strong>用例名称（可选）</Text>
              <Input
                placeholder="例如：登录功能测试"
                value={testName}
                onChange={(e) => setTestName(e.target.value)}
                style={{ marginTop: 8 }}
              />
            </div>

            <div>
              <Text strong>场景描述</Text>
              <TextArea
                placeholder="例如：打开应用，点击登录按钮，输入用户名和密码，点击提交按钮，验证登录成功"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                autoSize={{ minRows: 4, maxRows: 8 }}
                style={{ marginTop: 8 }}
              />
            </div>

            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={handleGenerate}
              loading={loading}
              block
            >
              生成测试用例
            </Button>

            <Divider />

            <div>
              <Space>
                <Text strong>使用模板</Text>
                <Button size="small" onClick={handleLoadTemplates}>
                  加载模板
                </Button>
              </Space>
              <Select
                placeholder="选择模板"
                value={selectedTemplate}
                onChange={setSelectedTemplate}
                style={{ width: '100%', marginTop: 8 }}
                options={templates.map((t) => ({
                  label: t.name,
                  value: t.id,
                }))}
              />
              {selectedTemplate && (
                <Button
                  type="default"
                  onClick={handleGenerateFromTemplate}
                  loading={loading}
                  style={{ marginTop: 8 }}
                  block
                >
                  从模板生成
                </Button>
              )}
            </div>
          </Space>
        </Card>

        {/* Right: Result */}
        <Card title="生成的测试用例" style={{ flex: 1 }}>
          <Spin spinning={loading}>
            {result ? (
              <Space direction="vertical" style={{ width: '100%' }} size="large">
                <div>
                  <Space>
                    <Text strong>{result.name}</Text>
                    <Tag color="blue">{result.test_type}</Tag>
                    <Tag>优先级: {result.priority}</Tag>
                  </Space>
                  <Paragraph type="secondary" style={{ marginTop: 8 }}>
                    {result.description}
                  </Paragraph>
                </div>

                {result.preconditions.length > 0 && (
                  <Alert
                    message="前置条件"
                    description={
                      <List
                        size="small"
                        dataSource={result.preconditions}
                        renderItem={(item) => <List.Item>{item}</List.Item>}
                      />
                    }
                    type="info"
                  />
                )}

                <div>
                  <Text strong>测试步骤 ({result.steps.length} 步)</Text>
                  <Table
                    dataSource={result.steps}
                    columns={stepColumns}
                    rowKey={(_, index) => `step-${index}`}
                    size="small"
                    pagination={false}
                    style={{ marginTop: 8 }}
                    scroll={{ x: 800 }}
                  />
                </div>

                {result.postconditions.length > 0 && (
                  <Alert
                    message="后置条件"
                    description={
                      <List
                        size="small"
                        dataSource={result.postconditions}
                        renderItem={(item) => <List.Item>{item}</List.Item>}
                      />
                    }
                    type="success"
                  />
                )}

                {result.tags.length > 0 && (
                  <div>
                    <Text strong>标签：</Text>
                    <Space>
                      {result.tags.map((tag) => (
                        <Tag key={tag}>{tag}</Tag>
                      ))}
                    </Space>
                  </div>
                )}

                <Divider />

                <Space>
                  <Button
                    icon={<BulbOutlined />}
                    onClick={handleGetSuggestions}
                    loading={loading}
                  >
                    改进建议
                  </Button>
                  <Select
                    value={exportFormat}
                    onChange={setExportFormat}
                    style={{ width: 100 }}
                    options={[
                      { label: 'Python', value: 'python' },
                      { label: 'JSON', value: 'json' },
                    ]}
                  />
                  <Button
                    icon={<DownloadOutlined />}
                    onClick={handleExport}
                    loading={loading}
                  >
                    导出脚本
                  </Button>
                </Space>

                {suggestions.length > 0 && (
                  <Collapse
                    items={[
                      {
                        key: 'suggestions',
                        label: `改进建议 (${suggestions.length})`,
                        children: (
                          <List
                            dataSource={suggestions}
                            renderItem={(item) => (
                              <List.Item>
                                <Space>
                                  <Tag
                                    color={
                                      item.severity === 'high'
                                        ? 'red'
                                        : item.severity === 'medium'
                                        ? 'orange'
                                        : 'blue'
                                    }
                                  >
                                    {item.type}
                                  </Tag>
                                  <Text>{item.message}</Text>
                                  {item.step_index !== null && (
                                    <Text type="secondary">
                                      (步骤 {item.step_index + 1})
                                    </Text>
                                  )}
                                </Space>
                              </List.Item>
                            )}
                          />
                        ),
                      },
                    ]}
                  />
                )}

                {exportedScript && (
                  <Collapse
                    items={[
                      {
                        key: 'script',
                        label: '导出的脚本',
                        children: (
                          <TextArea
                            value={exportedScript}
                            autoSize={{ minRows: 10, maxRows: 20 }}
                            readOnly
                            style={{ fontFamily: 'monospace' }}
                          />
                        ),
                      },
                    ]}
                  />
                )}
              </Space>
            ) : (
              <Text type="secondary">请输入测试场景描述并点击"生成测试用例"</Text>
            )}
          </Spin>
        </Card>
      </div>
    </div>
  )
}
