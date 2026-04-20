import { useCallback } from 'react'
import { create } from 'zustand'

// User role enum
export type UserRole = 'admin' | 'user' | 'viewer'

// User status enum
export type UserStatus = 'active' | 'inactive' | 'suspended'

// User interface
export interface User {
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

// Auth state interface
interface AuthState {
  // State - no tokens stored in frontend (using HTTP-only cookies)
  user: User | null
  isAuthenticated: boolean
  loading: boolean
  error: string | null

  // Actions
  login: (username: string, password: string) => Promise<boolean>
  logout: () => Promise<void>
  refreshTokens: () => Promise<boolean>
  setUser: (user: User | null) => void
  clearError: () => void
  checkAuth: () => Promise<void>
}

// API base URL
const API_BASE = '/api/v1'

// Helper to get CSRF token from cookie
function getCsrfToken(): string | null {
  const match = document.cookie.match(/csrf_token=([^;]+)/)
  return match ? match[1] : null
}

// Create auth store - NO persistence (tokens in HTTP-only cookies)
export const useAuthStore = create<AuthState>()((set, get) => ({
  // Initial state
  user: null,
  isAuthenticated: false,
  loading: false,
  error: null,

  // Login action
  login: async (username: string, password: string) => {
    set({ loading: true, error: null })

    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include', // Important: include cookies
        body: JSON.stringify({ username, password }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Login failed')
      }

      const data = await response.json()

      set({
        user: data.user,
        isAuthenticated: true,
        loading: false,
        error: null,
      })

      return true
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Login failed'
      set({
        loading: false,
        error: message,
        isAuthenticated: false,
      })
      return false
    }
  },

  // Logout action
  logout: async () => {
    try {
      // Call logout API to invalidate tokens and clear cookies
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch (error) {
      console.error('Logout API call failed:', error)
    }

    // Clear state regardless of API result
    set({
      user: null,
      isAuthenticated: false,
      error: null,
    })
  },

  // Refresh tokens - uses refresh token from HTTP-only cookie
  refreshTokens: async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        credentials: 'include', // Send refresh token cookie
      })

      if (!response.ok) {
        // Token refresh failed, logout user
        set({
          user: null,
          isAuthenticated: false,
        })
        return false
      }

      const data = await response.json()

      set({
        user: data.user,
      })

      return true
    } catch (error) {
      console.error('Token refresh failed:', error)
      set({
        user: null,
        isAuthenticated: false,
      })
      return false
    }
  },

  // Set user
  setUser: (user) => set({ user }),

  // Clear error
  clearError: () => set({ error: null }),

  // Check authentication status - verify with server using cookies
  checkAuth: async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/me`, {
        credentials: 'include', // Send cookies
      })

      if (response.ok) {
        const user: User = await response.json()
        set({ user, isAuthenticated: true })
      } else if (response.status === 401) {
        // Token might be expired, try refresh
        const refreshed = await get().refreshTokens()
        if (!refreshed) {
          set({ isAuthenticated: false, user: null })
        }
      } else {
        set({ isAuthenticated: false, user: null })
      }
    } catch (error) {
      console.error('Auth check failed:', error)
      set({ isAuthenticated: false, user: null })
    }
  },
}))

// Helper hook for authenticated fetch using cookies
export const useAuthenticatedFetch = () => {
  const { refreshTokens, logout } = useAuthStore()

  const fetchWithAuth = useCallback(async (url: string, options: RequestInit = {}) => {
    // Get CSRF token for state-changing requests
    const method = (options.method || 'GET').toUpperCase()
    const requiresCsrf = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)
    const csrfToken = getCsrfToken()

    const headers = new Headers(options.headers)

    // Add CSRF token header for state-changing requests
    if (requiresCsrf && csrfToken) {
      headers.set('X-CSRF-Token', csrfToken)
    }

    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include', // Send cookies
    })

    // If 401, try to refresh token
    if (response.status === 401) {
      const refreshed = await refreshTokens()
      if (refreshed) {
        // Retry with new token (new CSRF token will be in cookie)
        const newCsrfToken = getCsrfToken()
        const retryHeaders = new Headers(options.headers)
        if (requiresCsrf && newCsrfToken) {
          retryHeaders.set('X-CSRF-Token', newCsrfToken)
        }
        return fetch(url, {
          ...options,
          headers: retryHeaders,
          credentials: 'include',
        })
      } else {
        await logout()
        throw new Error('Session expired')
      }
    }

    return response
  }, [refreshTokens, logout])

  return fetchWithAuth
}

// Permission check helper
export const hasPermission = (user: User | null, permission: string): boolean => {
  if (!user) return false

  // Admin has all permissions
  if (user.role === 'admin') return true

  // Define permission rules
  const permissionMap: Record<string, UserRole[]> = {
    // Device permissions
    'device:read': ['admin', 'user', 'viewer'],
    'device:write': ['admin', 'user'],
    'device:delete': ['admin'],

    // Script permissions
    'script:read': ['admin', 'user', 'viewer'],
    'script:write': ['admin', 'user'],
    'script:execute': ['admin', 'user'],
    'script:delete': ['admin'],

    // Reservation permissions
    'reservation:read': ['admin', 'user', 'viewer'],
    'reservation:write': ['admin', 'user'],
    'reservation:cancel': ['admin', 'user'],

    // Schedule permissions
    'schedule:read': ['admin', 'user', 'viewer'],
    'schedule:write': ['admin', 'user'],
    'schedule:delete': ['admin'],

    // Parallel execution
    'parallel:execute': ['admin', 'user'],

    // Report permissions
    'report:read': ['admin', 'user', 'viewer'],
    'report:export': ['admin', 'user'],

    // User management
    'user:read': ['admin'],
    'user:write': ['admin'],
    'user:delete': ['admin'],

    // Alert management
    'alert:read': ['admin', 'user', 'viewer'],
    'alert:write': ['admin'],
    'alert:delete': ['admin'],
  }

  const allowedRoles = permissionMap[permission] || []
  return allowedRoles.includes(user.role)
}
