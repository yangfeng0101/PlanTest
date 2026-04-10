// AuthGuard - Route guard for protected pages
import { Navigate, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore, hasPermission } from '@/stores/authStore'
import { useEffect, useState } from 'react'

interface AuthGuardProps {
  children: React.ReactNode
  requiredPermission?: string
}

export default function AuthGuard({ children, requiredPermission }: AuthGuardProps) {
  const location = useLocation()
  const { isAuthenticated, user, loading, checkAuth } = useAuthStore()
  const [isChecking, setIsChecking] = useState(true)

  useEffect(() => {
    const verifyAuth = async () => {
      await checkAuth()
      setIsChecking(false)
    }
    verifyAuth()
  }, [checkAuth])

  // Show loading while checking auth
  if (isChecking || loading) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh'
      }}>
        <Spin size="large" tip="Loading..." />
      </div>
    )
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // Check permission if required
  if (requiredPermission && user) {
    if (!hasPermission(user, requiredPermission)) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
          gap: '16px'
        }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access this page.</p>
        </div>
      )
    }
  }

  return <>{children}</>
}
