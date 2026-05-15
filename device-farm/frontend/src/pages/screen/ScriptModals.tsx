import PlusOutlined from '@ant-design/icons/PlusOutlined'
import { Button, Form, Input, List, Modal, Select, Space, Tag, Typography } from 'antd'
import type { Script } from '@/types'
import { countScriptLines, formatDateTime } from './scriptWorkspace'

const { Text } = Typography

interface ScriptModalsProps {
  pickerOpen: boolean
  pickerLoading: boolean
  savedScripts: Script[]
  onClosePicker: () => void
  onCreateExampleScript: () => void
  onSelectSavedScript: (script: Script) => void
  saveOpen: boolean
  saving: boolean
  scriptName: string
  scriptTags: string[]
  scriptDescription: string
  onScriptNameChange: (value: string) => void
  onScriptTagsChange: (value: string[]) => void
  onScriptDescriptionChange: (value: string) => void
  onSaveScript: () => void
  onCloseSave: () => void
}

export default function ScriptModals({
  pickerOpen,
  pickerLoading,
  savedScripts,
  onClosePicker,
  onCreateExampleScript,
  onSelectSavedScript,
  saveOpen,
  saving,
  scriptName,
  scriptTags,
  scriptDescription,
  onScriptNameChange,
  onScriptTagsChange,
  onScriptDescriptionChange,
  onSaveScript,
  onCloseSave,
}: ScriptModalsProps) {
  return (
    <>
      <Modal
        title="选择已保存脚本"
        open={pickerOpen}
        footer={null}
        width={760}
        onCancel={onClosePicker}
      >
        <div className="script-picker-toolbar">
          <Space direction="vertical" size={2}>
            <Text strong>脚本来源</Text>
            <Text type="secondary">载入已有脚本，或新建脚本开始编写。</Text>
          </Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={onCreateExampleScript}>
            新建脚本
          </Button>
        </div>
        <List
          className="script-picker-list"
          loading={pickerLoading}
          dataSource={savedScripts}
          locale={{ emptyText: '暂无已保存脚本' }}
          renderItem={(script) => (
            <List.Item
              actions={[
                <Button key="load" size="small" type="primary" onClick={() => onSelectSavedScript(script)}>
                  载入
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space size="small" wrap>
                    <Text strong>{script.name}</Text>
                    <Tag>{script.script_type}</Tag>
                    {script.status ? <Tag color={script.status === 'active' ? 'success' : 'default'}>{script.status}</Tag> : null}
                  </Space>
                }
                description={
                  <Space direction="vertical" size={2}>
                    <Text type="secondary">{script.description || '无描述'}</Text>
                    <Text type="secondary">
                      更新：{formatDateTime(script.updated_at)} · {countScriptLines(script.content)} 行
                    </Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Modal>

      <Modal
        title="保存脚本"
        open={saveOpen}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        onOk={onSaveScript}
        onCancel={onCloseSave}
      >
        <Form layout="vertical">
          <Form.Item label="脚本名称" required>
            <Input value={scriptName} onChange={(event) => onScriptNameChange(event.target.value)} placeholder="请输入脚本名称" />
          </Form.Item>
          <Form.Item label="标签">
            <Select
              mode="tags"
              value={scriptTags}
              onChange={onScriptTagsChange}
              tokenSeparators={[',']}
              placeholder="输入标签后回车"
            />
          </Form.Item>
          <Form.Item label="描述">
            <Input.TextArea
              value={scriptDescription}
              rows={3}
              onChange={(event) => onScriptDescriptionChange(event.target.value)}
              placeholder="简单描述脚本用途"
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
