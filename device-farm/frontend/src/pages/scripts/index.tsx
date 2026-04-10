import { useState, useEffect } from 'react'
import { Card, Row, Col, Button, Table, Space, Modal, Form, Input, Select, Tag, message, Popconfirm } from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  CodeOutlined,
} from '@ant-design/icons'
import CodeEditor from '@/components/CodeEditor'
import { useScriptStore } from '@/stores/scriptStore'
import type { Script } from '@/types'

const { Option } = Select
const { TextArea } = Input

export default function ScriptsPage() {
  const { scripts, loading, fetchScripts, createScript, updateScript, deleteScript } = useScriptStore()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingScript, setEditingScript] = useState<Script | null>(null)
  const [code, setCode] = useState('')
  const [form] = Form.useForm()
  const [keyword, setKeyword] = useState('')

  useEffect(() => {
    fetchScripts()
  }, [fetchScripts])

  const handleCreate = () => {
    setEditingScript(null)
    setCode('# Python script\nprint("Hello, Device Farm!")')
    form.resetFields()
    form.setFieldsValue({ language: 'python' })
    setIsModalOpen(true)
  }

  const handleEdit = (script: Script) => {
    setEditingScript(script)
    setCode(script.content)
    form.setFieldsValue(script)
    setIsModalOpen(true)
  }

  const handleDelete = async (id: string) => {
    await deleteScript(id)
    message.success('脚本删除成功')
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const scriptData = {
        ...values,
        content: code,
      }

      if (editingScript) {
        await updateScript(editingScript.id, scriptData)
        message.success('脚本更新成功')
      } else {
        await createScript(scriptData)
        message.success('脚本创建成功')
      }
      setIsModalOpen(false)
    } catch (error) {
      console.error('Validation failed:', error)
    }
  }

  const handleRun = (script: Script) => {
    message.info(`正在运行脚本: ${script.name}`)
    // 这里应该调用后端执行脚本
  }

  const languageColors: Record<string, string> = {
    python: 'blue',
    javascript: 'gold',
    shell: 'green',
  }

  const columns = [
    {
      title: '脚本名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: Script) => (
        <a onClick={() => handleEdit(record)}>
          <CodeOutlined style={{ marginRight: 8 }} />
          {name}
        </a>
      ),
    },
    {
      title: '语言',
      dataIndex: 'language',
      key: 'language',
      render: (language: string) => (
        <Tag color={languageColors[language] || 'default'}>{language.toUpperCase()}</Tag>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      render: (tags: string[]) => (
        <>
          {tags.map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          ))}
        </>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updatedAt',
      key: 'updatedAt',
      width: 180,
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: unknown, record: Script) => (
        <Space>
          <Button type="link" icon={<PlayCircleOutlined />} onClick={() => handleRun(record)}>
            运行
          </Button>
          <Button type="link" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这个脚本吗?"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const filteredScripts = scripts.filter((script) =>
    script.name.toLowerCase().includes(keyword.toLowerCase()) ||
    script.description.toLowerCase().includes(keyword.toLowerCase())
  )

  return (
    <div>
      <Card
        title="脚本管理"
        extra={
          <Space>
            <Input.Search
              placeholder="搜索脚本"
              allowClear
              style={{ width: 250 }}
              onSearch={setKeyword}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              新建脚本
            </Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={filteredScripts}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal
        title={editingScript ? '编辑脚本' : '新建脚本'}
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        onOk={handleSave}
        width={900}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="name"
                label="脚本名称"
                rules={[{ required: true, message: '请输入脚本名称' }]}
              >
                <Input placeholder="请输入脚本名称" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="language"
                label="语言类型"
                rules={[{ required: true, message: '请选择语言类型' }]}
              >
                <Select placeholder="请选择语言类型">
                  <Option value="python">Python</Option>
                  <Option value="javascript">JavaScript</Option>
                  <Option value="shell">Shell</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="请输入脚本描述" />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入标签后按回车添加" />
          </Form.Item>
          <Form.Item label="脚本内容">
            <div style={{ border: '1px solid #d9d9d9', borderRadius: 4, overflow: 'hidden' }}>
              <CodeEditor
                value={code}
                language={form.getFieldValue('language') || 'python'}
                onChange={setCode}
              />
            </div>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
