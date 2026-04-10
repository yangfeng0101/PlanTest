import { useState, useEffect, useCallback } from 'react'
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Modal,
  Form,
  Input,
  Select,
  message,
  Popconfirm,
  Tooltip,
  Badge,
  Avatar,
} from 'antd'
import {
  ReloadOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  KeyOutlined,
  UserOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useAuthStore, hasPermission, type UserRole, type UserStatus } from '@/stores/authStore'

interface UserListItem {
  id: string
  username: string
  email: string
  role: UserRole
  status: UserStatus
  full_name?: string
  avatar_url?: string
  created_at: string
  last_login_at?: string
}

interface UserFormData {
  username: string
  email: string
  password?: string
  full_name?: string
  role: UserRole
}

const API_BASE = '/api/v1'

const getRoleTag = (role: UserRole) => {
  const roleConfig: Record<UserRole, { color: string; text: string }> = {
    admin: { color: 'red', text: 'Admin' },
    user: { color: 'blue', text: 'User' },
    viewer: { color: 'green', text: 'Viewer' },
  }
  const config = roleConfig[role] || { color: 'default', text: role }
  return <Tag color={config.color}>{config.text}</Tag>
}

const getStatusBadge = (status: UserStatus) => {
  const statusConfig: Record<UserStatus, { status: 'success' | 'error' | 'warning' | 'default'; text: string }> = {
    active: { status: 'success', text: 'Active' },
    inactive: { status: 'default', text: 'Inactive' },
    suspended: { status: 'warning', text: 'Suspended' },
  }
  const config = statusConfig[status] || { status: 'default', text: status }
  return <Badge status={config.status} text={config.text} />
}

export default function UsersPage() {
  const { user: currentUser, accessToken } = useAuthStore()
  const [users, setUsers] = useState<UserListItem[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 })
  const [filters, setFilters] = useState<{ role?: string; status?: string; keyword?: string }>({})

  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [roleModalVisible, setRoleModalVisible] = useState(false)
  const [passwordModalVisible, setPasswordModalVisible] = useState(false)
  const [selectedUser, setSelectedUser] = useState<UserListItem | null>(null)

  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()
  const [roleForm] = Form.useForm()
  const [passwordForm] = Form.useForm()

  // Check admin permission
  const canManageUsers = hasPermission(currentUser, 'user:write')

  const fetchWithAuth = useCallback(async (url: string, options: RequestInit = {}) => {
    if (!accessToken) {
      throw new Error('Not authenticated')
    }
    const response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || 'Request failed')
    }
    return response
  }, [accessToken])

  const fetchUsers = useCallback(async () => {
    if (!canManageUsers) {
      message.error('Access denied')
      return
    }

    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.set('page', String(pagination.current))
      params.set('page_size', String(pagination.pageSize))
      if (filters.role) params.set('role', filters.role)
      if (filters.status) params.set('status', filters.status)
      if (filters.keyword) params.set('keyword', filters.keyword)

      const response = await fetchWithAuth(`${API_BASE}/users?${params}`)
      const data = await response.json()
      setUsers(data.items || [])
      setPagination(prev => ({ ...prev, total: data.total || 0 }))
    } catch (error) {
      console.error('Failed to fetch users:', error)
      message.error('Failed to load users')
    } finally {
      setLoading(false)
    }
  }, [canManageUsers, fetchWithAuth, pagination.current, pagination.pageSize, filters])

  useEffect(() => {
    fetchUsers()
  }, [fetchUsers])

  const handleCreateUser = async (values: UserFormData) => {
    try {
      await fetchWithAuth(`${API_BASE}/users`, {
        method: 'POST',
        body: JSON.stringify(values),
      })
      message.success('User created successfully')
      setCreateModalVisible(false)
      createForm.resetFields()
      fetchUsers()
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to create user'
      message.error(msg)
    }
  }

  const handleUpdateUser = async (values: Partial<UserFormData>) => {
    if (!selectedUser) return

    try {
      await fetchWithAuth(`${API_BASE}/users/${selectedUser.id}`, {
        method: 'PATCH',
        body: JSON.stringify(values),
      })
      message.success('User updated successfully')
      setEditModalVisible(false)
      editForm.resetFields()
      fetchUsers()
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to update user'
      message.error(msg)
    }
  }

  const handleUpdateRole = async (values: { role: UserRole }) => {
    if (!selectedUser) return

    try {
      await fetchWithAuth(`${API_BASE}/users/${selectedUser.id}/role`, {
        method: 'PATCH',
        body: JSON.stringify(values),
      })
      message.success('Role updated successfully')
      setRoleModalVisible(false)
      roleForm.resetFields()
      fetchUsers()
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to update role'
      message.error(msg)
    }
  }

  const handleResetPassword = async (values: { password: string }) => {
    if (!selectedUser) return

    try {
      await fetchWithAuth(`${API_BASE}/users/${selectedUser.id}/reset-password`, {
        method: 'POST',
        body: JSON.stringify(values),
      })
      message.success('Password reset successfully')
      setPasswordModalVisible(false)
      passwordForm.resetFields()
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to reset password'
      message.error(msg)
    }
  }

  const handleDeleteUser = async (userId: string) => {
    try {
      await fetchWithAuth(`${API_BASE}/users/${userId}`, {
        method: 'DELETE',
      })
      message.success('User deleted successfully')
      fetchUsers()
    } catch (error) {
      const msg = error instanceof Error ? error.message : 'Failed to delete user'
      message.error(msg)
    }
  }

  const openEditModal = (user: UserListItem) => {
    setSelectedUser(user)
    editForm.setFieldsValue({
      username: user.username,
      email: user.email,
      full_name: user.full_name,
      status: user.status,
    })
    setEditModalVisible(true)
  }

  const openRoleModal = (user: UserListItem) => {
    setSelectedUser(user)
    roleForm.setFieldsValue({ role: user.role })
    setRoleModalVisible(true)
  }

  const openPasswordModal = (user: UserListItem) => {
    setSelectedUser(user)
    passwordForm.resetFields()
    setPasswordModalVisible(true)
  }

  const handleTableChange = (newPagination: { current?: number; pageSize?: number }) => {
    setPagination(prev => ({
      ...prev,
      current: newPagination.current || prev.current,
      pageSize: newPagination.pageSize || prev.pageSize,
    }))
  }

  const handleSearch = (keyword: string) => {
    setFilters(prev => ({ ...prev, keyword: keyword || undefined }))
    setPagination(prev => ({ ...prev, current: 1 }))
  }

  const columns: ColumnsType<UserListItem> = [
    {
      title: 'User',
      key: 'user',
      width: 200,
      render: (_, record) => (
        <Space>
          <Avatar
            size="small"
            icon={<UserOutlined />}
            src={record.avatar_url}
          />
          <div>
            <div style={{ fontWeight: 500 }}>{record.username}</div>
            <div style={{ fontSize: 12, color: '#999' }}>{record.full_name}</div>
          </div>
        </Space>
      ),
    },
    {
      title: 'Email',
      dataIndex: 'email',
      key: 'email',
      width: 200,
    },
    {
      title: 'Role',
      dataIndex: 'role',
      key: 'role',
      width: 100,
      render: (role: UserRole) => getRoleTag(role),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: UserStatus) => getStatusBadge(status),
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) => date ? new Date(date).toLocaleString() : '-',
    },
    {
      title: 'Last Login',
      dataIndex: 'last_login_at',
      key: 'last_login_at',
      width: 180,
      render: (date: string) => date ? new Date(date).toLocaleString() : '-',
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_, record) => {
        const isSelf = currentUser?.id === record.id
        return (
          <Space size="small">
            <Tooltip title="Edit">
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => openEditModal(record)}
              />
            </Tooltip>
            <Tooltip title="Change Role">
              <Button
                type="text"
                size="small"
                icon={<UserOutlined />}
                onClick={() => openRoleModal(record)}
                disabled={isSelf}
              />
            </Tooltip>
            <Tooltip title="Reset Password">
              <Button
                type="text"
                size="small"
                icon={<KeyOutlined />}
                onClick={() => openPasswordModal(record)}
              />
            </Tooltip>
            <Popconfirm
              title="Delete user?"
              description="This action cannot be undone."
              onConfirm={() => handleDeleteUser(record.id)}
              okText="Yes"
              cancelText="No"
              disabled={isSelf}
            >
              <Tooltip title="Delete">
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  disabled={isSelf}
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        )
      },
    },
  ]

  if (!canManageUsers) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: 40 }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access this page.</p>
        </div>
      </Card>
    )
  }

  return (
    <div>
      <Card
        title="User Management"
        extra={
          <Space>
            <Input.Search
              placeholder="Search users..."
              allowClear
              onSearch={handleSearch}
              style={{ width: 200 }}
              prefix={<SearchOutlined />}
            />
            <Select
              placeholder="Role"
              allowClear
              style={{ width: 100 }}
              onChange={(value) => setFilters(prev => ({ ...prev, role: value || undefined }))}
              options={[
                { value: 'admin', label: 'Admin' },
                { value: 'user', label: 'User' },
                { value: 'viewer', label: 'Viewer' },
              ]}
            />
            <Select
              placeholder="Status"
              allowClear
              style={{ width: 100 }}
              onChange={(value) => setFilters(prev => ({ ...prev, status: value || undefined }))}
              options={[
                { value: 'active', label: 'Active' },
                { value: 'inactive', label: 'Inactive' },
                { value: 'suspended', label: 'Suspended' },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={fetchUsers}>
              Refresh
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>
              Add User
            </Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={users}
          rowKey="id"
          loading={loading}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} users`,
          }}
          onChange={handleTableChange}
        />
      </Card>

      {/* Create User Modal */}
      <Modal
        title="Create User"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false)
          createForm.resetFields()
        }}
        onOk={() => createForm.submit()}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreateUser}
        >
          <Form.Item
            name="username"
            label="Username"
            rules={[
              { required: true, message: 'Please input username' },
              { min: 3, message: 'Username must be at least 3 characters' },
            ]}
          >
            <Input placeholder="Enter username" />
          </Form.Item>
          <Form.Item
            name="email"
            label="Email"
            rules={[
              { required: true, message: 'Please input email' },
              { type: 'email', message: 'Invalid email format' },
            ]}
          >
            <Input placeholder="Enter email" />
          </Form.Item>
          <Form.Item
            name="password"
            label="Password"
            rules={[
              { required: true, message: 'Please input password' },
              { min: 6, message: 'Password must be at least 6 characters' },
            ]}
          >
            <Input.Password placeholder="Enter password" />
          </Form.Item>
          <Form.Item
            name="full_name"
            label="Full Name"
          >
            <Input placeholder="Enter full name" />
          </Form.Item>
          <Form.Item
            name="role"
            label="Role"
            initialValue="user"
            rules={[{ required: true, message: 'Please select role' }]}
          >
            <Select
              options={[
                { value: 'admin', label: 'Admin' },
                { value: 'user', label: 'User' },
                { value: 'viewer', label: 'Viewer' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit User Modal */}
      <Modal
        title="Edit User"
        open={editModalVisible}
        onCancel={() => {
          setEditModalVisible(false)
          editForm.resetFields()
        }}
        onOk={() => editForm.submit()}
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleUpdateUser}
        >
          <Form.Item
            name="username"
            label="Username"
            rules={[
              { required: true, message: 'Please input username' },
              { min: 3, message: 'Username must be at least 3 characters' },
            ]}
          >
            <Input placeholder="Enter username" />
          </Form.Item>
          <Form.Item
            name="email"
            label="Email"
            rules={[
              { required: true, message: 'Please input email' },
              { type: 'email', message: 'Invalid email format' },
            ]}
          >
            <Input placeholder="Enter email" />
          </Form.Item>
          <Form.Item
            name="full_name"
            label="Full Name"
          >
            <Input placeholder="Enter full name" />
          </Form.Item>
          <Form.Item
            name="status"
            label="Status"
            rules={[{ required: true, message: 'Please select status' }]}
          >
            <Select
              options={[
                { value: 'active', label: 'Active' },
                { value: 'inactive', label: 'Inactive' },
                { value: 'suspended', label: 'Suspended' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Change Role Modal */}
      <Modal
        title="Change Role"
        open={roleModalVisible}
        onCancel={() => {
          setRoleModalVisible(false)
          roleForm.resetFields()
        }}
        onOk={() => roleForm.submit()}
      >
        <Form
          form={roleForm}
          layout="vertical"
          onFinish={handleUpdateRole}
        >
          <Form.Item
            name="role"
            label="Role"
            rules={[{ required: true, message: 'Please select role' }]}
          >
            <Select
              options={[
                { value: 'admin', label: 'Admin' },
                { value: 'user', label: 'User' },
                { value: 'viewer', label: 'Viewer' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Reset Password Modal */}
      <Modal
        title="Reset Password"
        open={passwordModalVisible}
        onCancel={() => {
          setPasswordModalVisible(false)
          passwordForm.resetFields()
        }}
        onOk={() => passwordForm.submit()}
      >
        <Form
          form={passwordForm}
          layout="vertical"
          onFinish={handleResetPassword}
        >
          <Form.Item
            name="password"
            label="New Password"
            rules={[
              { required: true, message: 'Please input new password' },
              { min: 6, message: 'Password must be at least 6 characters' },
            ]}
          >
            <Input.Password placeholder="Enter new password" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
