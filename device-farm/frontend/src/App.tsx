import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Menu, Dropdown, Avatar, Space } from 'antd'
import MobileOutlined from '@ant-design/icons/MobileOutlined'
import CodeOutlined from '@ant-design/icons/CodeOutlined'
import FileTextOutlined from '@ant-design/icons/FileTextOutlined'
import TeamOutlined from '@ant-design/icons/TeamOutlined'
import LogoutOutlined from '@ant-design/icons/LogoutOutlined'
import UserOutlined from '@ant-design/icons/UserOutlined'
import SettingOutlined from '@ant-design/icons/SettingOutlined'
import RobotOutlined from '@ant-design/icons/RobotOutlined'
import ScanOutlined from '@ant-design/icons/ScanOutlined'
import AimOutlined from '@ant-design/icons/AimOutlined'
import ThunderboltOutlined from '@ant-design/icons/ThunderboltOutlined'
import UsergroupAddOutlined from '@ant-design/icons/UsergroupAddOutlined'
import AlertOutlined from '@ant-design/icons/AlertOutlined'
import DashboardOutlined from '@ant-design/icons/DashboardOutlined'
import DevicesPage from './pages/devices'
import DeviceDetailPage from './pages/devices/Detail'
import ScreenPage from './pages/screen'
import ScriptsPage from './pages/scripts'
import ReportsPage from './pages/reports'
import TrendPage from './pages/reports/Trend'
import ParallelExecutionPage from './pages/parallel'
import LoginPage from './pages/auth/Login'
import OCRPage from './pages/ai/OCR'
import LocatePage from './pages/ai/Locate'
import GeneratePage from './pages/ai/Generate'
import UsersPage from './pages/admin/Users'
import AlertsPage from './pages/alerts'
import MonitoringPage from './pages/monitoring'
import AuthGuard from './components/AuthGuard'
import { useAuthStore, hasPermission } from './stores/authStore'
import './App.css'

const { Sider, Content, Header } = Layout

const baseMenuItems = [
  {
    key: '/devices',
    icon: <MobileOutlined />,
    label: '设备管理',
  },
  {
    key: '/monitoring',
    icon: <DashboardOutlined />,
    label: '设备监控',
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
  {
    key: '/ai',
    icon: <RobotOutlined />,
    label: 'AI 工具',
    children: [
      {
        key: '/ai/ocr',
        icon: <ScanOutlined />,
        label: 'OCR 识别',
      },
      {
        key: '/ai/locate',
        icon: <AimOutlined />,
        label: '元素定位',
      },
      {
        key: '/ai/generate',
        icon: <ThunderboltOutlined />,
        label: '用例生成',
      },
    ],
  },
  {
    key: '/admin/users',
    icon: <UsergroupAddOutlined />,
    label: '用户管理',
    permission: 'user:read',
  },
  {
    key: '/alerts',
    icon: <AlertOutlined />,
    label: '告警配置',
    permission: 'alert:read',
  },
]

// Main layout component with auth
function MainLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuthStore()
  const isScreenWorkspace = location.pathname === '/screen'

  // Filter menu items based on permissions
  const menuItems = baseMenuItems.filter(item => {
    if (item.permission) {
      return hasPermission(user, item.permission)
    }
    return true
  })

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
      {!isScreenWorkspace && (
        <Sider width={220} theme="light">
          <div className="logo">
            <MobileOutlined style={{ fontSize: 24, color: '#1890ff' }} />
            <span>设备农场</span>
          </div>
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            defaultOpenKeys={['/ai']}
            items={menuItems}
            onClick={({ key }) => {
              navigate(key)
            }}
          />
        </Sider>
      )}
      <Layout>
        {!isScreenWorkspace && (
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
        )}
        <Content
          style={{
            padding: isScreenWorkspace ? 0 : 24,
            overflow: 'auto',
          }}
        >
          <Routes>
            <Route path="/devices" element={<DevicesPage />} />
            <Route path="/devices/:id" element={<DeviceDetailPage />} />
            <Route path="/monitoring" element={<MonitoringPage />} />
            <Route path="/screen" element={<ScreenPage />} />
            <Route path="/scripts" element={<ScriptsPage />} />
            <Route path="/parallel" element={<ParallelExecutionPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/reports/trend" element={<TrendPage />} />
            <Route path="/ai/ocr" element={<OCRPage />} />
            <Route path="/ai/locate" element={<LocatePage />} />
            <Route path="/ai/generate" element={<GeneratePage />} />
            <Route path="/admin/users" element={<UsersPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
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
