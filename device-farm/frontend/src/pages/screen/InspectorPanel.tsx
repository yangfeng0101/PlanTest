import ReloadOutlined from '@ant-design/icons/ReloadOutlined'
import { Button, Segmented, Space, Switch, Table, Typography } from 'antd'
import type { UIElementNode } from './types'
import { STATIC_AUTO_REFRESH_INTERVAL_OPTIONS } from './api'

const { Text } = Typography

interface InspectorPanelProps {
  selectedDevice: string
  inspectReady: boolean
  uiHierarchySupported: boolean
  loadingUiHierarchy: boolean
  onFetchUiHierarchy: () => void
  isIosStaticDebug: boolean
  screenshotSupported: boolean
  staticScreenshotLoading: boolean
  onRefreshScreenshot: () => void
  staticAutoRefresh: boolean
  staticAutoRefreshIntervalMs: number
  staticScreenshot: string | null
  staticActionLoading: boolean
  onStaticAutoRefreshChange: (checked: boolean) => void
  onStaticAutoRefreshIntervalChange: (value: number) => void
  isIosStaticActionSupported: boolean
  iosTapMode: boolean
  iosSwipeMode: boolean
  onIosTapModeChange: (checked: boolean) => void
  onIosSwipeModeChange: (checked: boolean) => void
  selectedUiElement: UIElementNode | null
  uiElements: UIElementNode[]
  onTapSelectedUiElement: () => void
  onLongPressSelectedUiElement: () => void
  onClearUiHierarchy: () => void
  currentDeviceLabel: string
}

function buildUiPropertyRows(selectedUiElement: UIElementNode | null) {
  return selectedUiElement
    ? [
        { key: 'uid', property: 'uid', value: selectedUiElement.uid },
        { key: 'class', property: 'class', value: selectedUiElement.class_name },
        { key: 'resource_id', property: 'resource-id', value: selectedUiElement.resource_id },
        { key: 'text', property: 'text', value: selectedUiElement.text },
        { key: 'content_desc', property: 'content-desc', value: selectedUiElement.content_desc },
        { key: 'package', property: 'package', value: selectedUiElement.package },
        {
          key: 'bounds',
          property: 'bounds',
          value: `[${selectedUiElement.bounds.x},${selectedUiElement.bounds.y}][${selectedUiElement.bounds.x + selectedUiElement.bounds.width},${selectedUiElement.bounds.y + selectedUiElement.bounds.height}]`,
        },
        { key: 'center', property: 'center', value: `${selectedUiElement.center.x}, ${selectedUiElement.center.y}` },
        { key: 'clickable', property: 'clickable', value: String(selectedUiElement.clickable) },
        { key: 'enabled', property: 'enabled', value: String(selectedUiElement.enabled) },
        { key: 'selected', property: 'selected', value: String(selectedUiElement.selected) },
        { key: 'focused', property: 'focused', value: String(selectedUiElement.focused) },
        { key: 'scrollable', property: 'scrollable', value: String(selectedUiElement.scrollable) },
        { key: 'xpath', property: 'xpath', value: selectedUiElement.xpath },
        {
          key: 'selectors',
          property: 'selector_suggestions',
          value: selectedUiElement.selector_suggestions.map((s) => `${s.type}: ${s.value}`).join('\n'),
        },
      ]
    : []
}

export default function InspectorPanel({
  selectedDevice,
  inspectReady,
  uiHierarchySupported,
  loadingUiHierarchy,
  onFetchUiHierarchy,
  isIosStaticDebug,
  screenshotSupported,
  staticScreenshotLoading,
  onRefreshScreenshot,
  staticAutoRefresh,
  staticAutoRefreshIntervalMs,
  staticScreenshot,
  staticActionLoading,
  onStaticAutoRefreshChange,
  onStaticAutoRefreshIntervalChange,
  isIosStaticActionSupported,
  iosTapMode,
  iosSwipeMode,
  onIosTapModeChange,
  onIosSwipeModeChange,
  selectedUiElement,
  uiElements,
  onTapSelectedUiElement,
  onLongPressSelectedUiElement,
  onClearUiHierarchy,
  currentDeviceLabel,
}: InspectorPanelProps) {
  const uiPropertyRows = buildUiPropertyRows(selectedUiElement)

  return (
    <>
      <div className="workspace-panel inspector-panel">
        <div className="workspace-toolbar">
          <Space>
            <Button type="primary" loading={loadingUiHierarchy} disabled={!selectedDevice || !inspectReady || !uiHierarchySupported} onClick={onFetchUiHierarchy}>
              获取控件
            </Button>
            {isIosStaticDebug && (
              <Button icon={<ReloadOutlined />} loading={staticScreenshotLoading} disabled={!selectedDevice || !screenshotSupported} onClick={onRefreshScreenshot}>
                刷新截图
              </Button>
            )}
            {isIosStaticDebug && (
              <Space size={6}>
                <Text type="secondary">自动刷新</Text>
                <Switch
                  size="small"
                  checked={staticAutoRefresh}
                  disabled={!staticScreenshot || staticActionLoading || loadingUiHierarchy}
                  onChange={onStaticAutoRefreshChange}
                />
                <Segmented
                  size="small"
                  value={staticAutoRefreshIntervalMs}
                  options={STATIC_AUTO_REFRESH_INTERVAL_OPTIONS}
                  disabled={!staticAutoRefresh}
                  onChange={(value) => onStaticAutoRefreshIntervalChange(Number(value))}
                />
              </Space>
            )}
            {isIosStaticDebug && isIosStaticActionSupported && (
              <>
                <Space size={6}>
                  <Text type="secondary">点按模式</Text>
                  <Switch
                    size="small"
                    checked={iosTapMode}
                    disabled={staticActionLoading || (isIosStaticDebug && !staticScreenshot)}
                    onChange={onIosTapModeChange}
                  />
                </Space>
                <Space size={6}>
                  <Text type="secondary">滑动模式</Text>
                  <Switch
                    size="small"
                    checked={iosSwipeMode}
                    disabled={staticActionLoading || (isIosStaticDebug && !staticScreenshot)}
                    onChange={onIosSwipeModeChange}
                  />
                </Space>
                <Button
                  disabled={!selectedUiElement || staticActionLoading}
                  loading={staticActionLoading}
                  onClick={onTapSelectedUiElement}
                >
                  点击控件
                </Button>
                <Button
                  disabled={!selectedUiElement || staticActionLoading}
                  loading={staticActionLoading}
                  onClick={onLongPressSelectedUiElement}
                >
                  长按控件
                </Button>
              </>
            )}
            <Button danger disabled={uiElements.length === 0} onClick={onClearUiHierarchy}>
              清理控件
            </Button>
          </Space>
          <Space size={20}>
            <Text type="secondary">当前设备：{currentDeviceLabel}</Text>
            <Text type="secondary">选中：{selectedUiElement?.class_name || '-'}</Text>
          </Space>
        </div>

        <Table
          className="ui-property-table"
          size="small"
          pagination={false}
          rowKey="key"
          columns={[
            {
              title: '属性',
              dataIndex: 'property',
              width: 180,
            },
            {
              title: '值',
              dataIndex: 'value',
              render: (value: string) => value ? (
                <Text copyable={{ text: value }} className="property-value">
                  {value}
                </Text>
              ) : (
                <Text type="secondary">空</Text>
              ),
            },
          ]}
          dataSource={uiPropertyRows}
          locale={{ emptyText: uiElements.length > 0 ? '点击左侧控件框查看属性' : '暂无数据' }}
        />
      </div>

      <div className="workspace-panel log-panel">
        <div className="workspace-toolbar compact">
          <Text strong>自动化选择器</Text>
          <Text type="secondary">点击属性值右侧图标可复制</Text>
        </div>
        <div className="selector-preview">
          {selectedUiElement ? (
            <>
              {selectedUiElement.selector_suggestions.map((selector) => (
                <div className="selector-row" key={`${selector.type}-${selector.value}`}>
                  <Text className="selector-type">{selector.type}</Text>
                  <Text copyable={{ text: selector.value }} className="selector-value">{selector.value}</Text>
                </div>
              ))}
            </>
          ) : (
            <Text type="secondary">选择控件后显示可用于自动化脚本的 selector。</Text>
          )}
        </div>
      </div>
    </>
  )
}
