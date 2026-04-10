import { create } from 'zustand'
import { persist } from 'zustand/middleware'

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

// Token response
export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: User
}

// Auth state interface
interface AuthState {
  // State
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  loading: boolean
  error: string | null

  // Actions
  login: (username: string, password: string) => Promise<boolean>
  logout: () => Promise<void>
  refreshTokens: () => Promise<boolean>
  setUser: (user: User | null) => void
  setTokens: (accessToken: string | null, refreshToken: string | null) => void
  clearError: () => void
  checkAuth: () => Promise<void>
}

// API base URL
const API_BASE = '/api/v1'

// Create auth store with persistence
export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      user: null,
      accessToken: null,
      refreshToken: null,
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
            body: JSON.stringify({ username, password }),
          })

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}))
            throw new Error(errorData.detail || 'Login failed')
          }

          const data: TokenResponse = await response.json()

          set({
            user: data.user,
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
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
        const { accessToken } = get()

        try {
          // Call logout API to invalidate token
          if (accessToken) {
            await fetch(`${API_BASE}/auth/logout`, {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${accessToken}`,
              },
            })
          }
        } catch (error) {
          console.error('Logout API call failed:', error)
        }

        // Clear state regardless of API result
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        })
      },

      // Refresh tokens
      refreshTokens: async () => {
        const { refreshToken } = get()

        if (!refreshToken) {
          return false
        }

        try {
          const response = await fetch(`${API_BASE}/auth/refresh`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ refresh_token: refreshToken }),
          })

          if (!response.ok) {
            // Token refresh failed, logout user
            set({
              user: null,
              accessToken: null,
              refreshToken: null,
              isAuthenticated: false,
            })
            return false
          }

          const data: TokenResponse = await response.json()

          set({
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            user: data.user,
          })

          return true
        } catch (error) {
          console.error('Token refresh failed:', error)
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
          })
          return false
        }
      },

      // Set user
      setUser: (user) => set({ user }),

      // Set tokens
      setTokens: (accessToken, refreshToken) =>
        set({ accessToken, refreshToken }),

      // Clear error
      clearError: () => set({ error: null }),

      // Check authentication status
      checkAuth: async () => {
        const { accessToken, refreshToken } = get()

        if (!accessToken && !refreshToken) {
          set({ isAuthenticated: false })
          return
        }

        // If we have tokens, try to get current user
        try {
          const response = await fetch(`${API_BASE}/auth/me`, {
            headers: {
              'Authorization': `Bearer ${accessToken}`,
            },
          })

          if (response.ok) {
            const user: User = await response.json()
            set({ user, isAuthenticated: true })
          } else {
            // Token might be expired, try refresh
            const refreshed = await get().refreshTokens()
            if (!refreshed) {
              set({ isAuthenticated: false })
            }
          }
        } catch (error) {
          console.error('Auth check failed:', error)
          set({ isAuthenticated: false })
        }
      },
    }),
    {
      name: 'auth-storage', // localStorage key
      partialize: (state) => ({
        // Only persist these fields
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)

// Helper hook for authenticated fetch
export const useAuthenticatedFetch = () => {
  const { accessToken, refreshTokens, logout } = useAuthStore()

  const fetchWithAuth = async (url: string, options: RequestInit = {}) => {
    if (!accessToken) {
      throw new Error('Not authenticated')
    }

    const response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        'Authorization': `Bearer ${accessToken}`,
      },
    })

    // If 401, try to refresh token
    if (response.status === 401) {
      const refreshed = await refreshTokens()
      if (refreshed) {
        // Retry with new token
        const newAccessToken = useAuthStore.getState().accessToken
        return fetch(url, {
          ...options,
          headers: {
            ...options.headers,
            'Authorization': `Bearer ${newAccessToken}`,
          },
        })
      } else {
        await logout()
        throw new Error('Session expired')
      }
    }

    return response
  }

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
