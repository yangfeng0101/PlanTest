import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Menu, Dropdown, Avatar, Space } from 'antd'
import {
  MobileOutlined,
  PlayCircleOutlined,
  CodeOutlined,
  FileTextOutlined,
  TeamOutlined,
  LogoutOutlined,
  UserOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import DevicesPage from './pages/devices'
import DeviceDetailPage from './pages/devices/Detail'
import ScreenPage from './pages/screen'
import ScriptsPage from './pages/scripts'
import ReportsPage from './pages/reports'
import ParallelExecutionPage from './pages/parallel'
import LoginPage from './pages/auth/Login'
import AuthGuard from './components/AuthGuard'
import { useAuthStore } from './stores/authStore'
import './App.css'

const { Sider, Content, Header } = Layout

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
    key: '/parallel',
    icon: <TeamOutlined />,
    label: '并行执行',
  },
  {
    key: '/reports',
    icon: <FileTextOutlined />,
    label: '测试报告',
  },
]

// Main layout component with auth
function MainLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuthStore()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人资料',
    },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: '设置',
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
    },
  ]

  const handleUserMenuClick = ({ key }: { key: string }) => {
    if (key === 'logout') {
      handleLogout()
    }
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="light">
        <div className="logo">
          <MobileOutlined style={{ fontSize: 24, color: '#1890ff' }} />
          <span>设备农场</span>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => {
            navigate(key)
          }}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <div style={{ flex: 1 }} />
          <Dropdown
            menu={{ items: userMenuItems, onClick: handleUserMenuClick }}
            placement="bottomRight"
          >
            <Space className="user-info" style={{ cursor: 'pointer' }}>
              <Avatar
                size="small"
                icon={<UserOutlined />}
                src={user?.avatar_url}
              />
              <span>{user?.full_name || user?.username || 'User'}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ padding: 24, overflow: 'auto' }}>
          <Routes>
            <Route path="/devices" element={<DevicesPage />} />
            <Route path="/devices/:id" element={<DeviceDetailPage />} />
            <Route path="/screen" element={<ScreenPage />} />
            <Route path="/scripts" element={<ScriptsPage />} />
            <Route path="/parallel" element={<ParallelExecutionPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/" element={<Navigate to="/devices" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Login route - no auth required */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected routes - require authentication */}
        <Route
          path="/*"
          element={
            <AuthGuard>
              <MainLayout />
            </AuthGuard>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}

export default App
