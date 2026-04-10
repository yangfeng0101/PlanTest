import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import {
  MobileOutlined,
  PlayCircleOutlined,
  CodeOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import DevicesPage from './pages/devices'
import DeviceDetailPage from './pages/devices/Detail'
import ScreenPage from './pages/screen'
import ScriptsPage from './pages/scripts'
import ReportsPage from './pages/reports'
import './App.css'

const { Sider, Content } = Layout

const menuItems = [
  {
    key: '/devices',
    icon: <MobileOutlined />,
    label: '设备管理',
  },
  {
    key: '/screen',
    icon: <PlayCircleOutlined />,
    label: '投屏控制',
  },
  {
    key: '/scripts',
    icon: <CodeOutlined />,
    label: '脚本管理',
  },
  {
    key: '/reports',
    icon: <FileTextOutlined />,
    label: '测试报告',
  },
]

function App() {
  return (
    <BrowserRouter>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider width={220} theme="light">
          <div className="logo">
            <MobileOutlined style={{ fontSize: 24, color: '#1890ff' }} />
            <span>设备农场</span>
          </div>
          <Menu
            mode="inline"
            defaultSelectedKeys={['/devices']}
            items={menuItems}
            onClick={({ key }) => {
              window.location.href = key
            }}
          />
        </Sider>
        <Content style={{ padding: 24, overflow: 'auto' }}>
          <Routes>
            <Route path="/devices" element={<DevicesPage />} />
            <Route path="/devices/:id" element={<DeviceDetailPage />} />
            <Route path="/screen" element={<ScreenPage />} />
            <Route path="/scripts" element={<ScriptsPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/" element={<Navigate to="/devices" replace />} />
          </Routes>
        </Content>
      </Layout>
    </BrowserRouter>
  )
}

export default App
