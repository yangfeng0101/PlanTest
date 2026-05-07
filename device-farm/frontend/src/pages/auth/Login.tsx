import { useState } from 'react'
import { Form, Input, Button, Card, message, Typography } from 'antd'
import UserOutlined from '@ant-design/icons/UserOutlined'
import LockOutlined from '@ant-design/icons/LockOutlined'
import CloudServerOutlined from '@ant-design/icons/CloudServerOutlined'
import { useAuthStore } from '@/stores/authStore'
import './Login.css'

const { Title, Text } = Typography

interface LoginForm {
  username: string
  password: string
}

export default function LoginPage() {
  const [form] = Form.useForm<LoginForm>()
  const [loading, setLoading] = useState(false)
  const { login, error, clearError } = useAuthStore()

  const handleSubmit = async (values: LoginForm) => {
    setLoading(true)
    clearError()

    try {
      const success = await login(values.username, values.password)

      if (success) {
        message.success('登录成功')
        // Redirect to home page
        window.location.href = '/devices'
      } else {
        message.error(error || '登录失败，请检查用户名和密码')
      }
    } catch {
      message.error('登录失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-container">
      <div className="login-background">
        <div className="login-card-wrapper">
          <Card className="login-card" bordered={false}>
            <div className="login-header">
              <CloudServerOutlined className="login-icon" />
              <Title level={2} className="login-title">
                云测
              </Title>
              <Text type="secondary" className="login-subtitle">
                移动设备云测试平台
              </Text>
            </div>

            <Form
              form={form}
              layout="vertical"
              onFinish={handleSubmit}
              autoComplete="off"
              size="large"
            >
              <Form.Item
                name="username"
                rules={[
                  { required: true, message: '请输入用户名' },
                  { min: 3, message: '用户名至少3个字符' },
                ]}
              >
                <Input
                  prefix={<UserOutlined />}
                  placeholder="用户名"
                  autoComplete="username"
                />
              </Form.Item>

              <Form.Item
                name="password"
                rules={[
                  { required: true, message: '请输入密码' },
                  { min: 6, message: '密码至少6个字符' },
                ]}
              >
                <Input.Password
                  prefix={<LockOutlined />}
                  placeholder="密码"
                  autoComplete="current-password"
                />
              </Form.Item>

              <Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={loading}
                  block
                  className="login-button"
                >
                  登录
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </div>
      </div>
    </div>
  )
}
