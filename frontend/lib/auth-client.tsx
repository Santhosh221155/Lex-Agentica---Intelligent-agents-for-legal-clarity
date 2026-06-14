import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import {
  AuthSession,
  AuthUser,
  clearTokens,
  loginRequest,
  meRequest,
  refreshRequest,
  registerRequest,
} from './auth'

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

type AuthContextValue = {
  status: AuthStatus
  user: AuthUser | null
  accessToken: string | null
  refreshToken: string | null
  login: (username: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshSession: () => Promise<AuthSession | null>
  authFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

async function loadProfile() {
  try {
    const user = await meRequest()
    return { user, accessToken: null, refreshToken: null }
  } catch {
    try {
      const refreshed = await refreshRequest()
      const user = await meRequest()
      return { user, accessToken: refreshed.access_token, refreshToken: refreshed.refresh_token }
    } catch {
      clearTokens()
      return null
    }
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [refreshToken, setRefreshToken] = useState<string | null>(null)

  async function applySession(session: AuthSession | null) {
    if (!session) {
      setStatus('unauthenticated')
      setUser(null)
      setAccessToken(null)
      setRefreshToken(null)
      return
    }

    // No need to persist tokens to storage - backend sets httpOnly cookies
    setStatus('authenticated')
    setUser(session.user)
    setAccessToken(session.accessToken)
    setRefreshToken(session.refreshToken)
  }

  useEffect(() => {
    let cancelled = false
    const bootstrap = async () => {
      // Try to load profile using httpOnly cookies (no need to check stored tokens)
      const loaded = await loadProfile()
      if (!cancelled) {
        if (loaded) {
          setStatus('authenticated')
          setUser(loaded.user)
          setAccessToken(loaded.accessToken)
          setRefreshToken(loaded.refreshToken)
        } else {
          setStatus('unauthenticated')
        }
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  async function refreshSession() {
    // With httpOnly cookies, refresh is automatic - just try to get profile
    try {
      const loaded = await loadProfile()
      if (loaded) {
        setStatus('authenticated')
        setUser(loaded.user)
        setAccessToken(loaded.accessToken)
        setRefreshToken(loaded.refreshToken)
        return { accessToken: loaded.accessToken, refreshToken: loaded.refreshToken, user: loaded.user }
      } else {
        await applySession(null)
        return null
      }
    } catch {
      await applySession(null)
      return null
    }
  }

  async function login(username: string, password: string) {
    // Backend will set httpOnly cookies automatically
    await loginRequest(username, password)
    // Now get the user profile using the cookies
    const profile = await meRequest()
    await applySession({ accessToken: null, refreshToken: null, user: profile })
  }

  async function register(username: string, email: string, password: string) {
    // Backend will set httpOnly cookies automatically
    await registerRequest(username, email, password)
    // Now get the user profile using the cookies
    const profile = await meRequest()
    await applySession({ accessToken: null, refreshToken: null, user: profile })
  }

  async function logout() {
    try {
      // Call logout-cleanup endpoint to clear user documents from Chroma/PostgreSQL/filesystem
      await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'}/api/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch {
      // best effort
    }
    clearTokens()
    await applySession(null)
  }

  async function authFetch(input: RequestInfo | URL, init: RequestInit = {}) {
    const headers = new Headers(init.headers || {})
    // Don't set Authorization header manually - cookies will be sent automatically
    // Only use accessToken if explicitly provided for backward compatibility
    if (accessToken) {
      headers.set('Authorization', `Bearer ${accessToken}`)
    }

    let response = await fetch(input, { ...init, headers, credentials: 'include' })
    if (response.status === 401) {
      const refreshed = await refreshSession()
      if (refreshed) {
        return fetch(input, { ...init, headers, credentials: 'include' })
      }
      await applySession(null)
    }
    return response
  }

  const value = useMemo<AuthContextValue>(() => ({
    status,
    user,
    accessToken: null, // httpOnly cookies handle this now
    refreshToken: null, // httpOnly cookies handle this now
    login,
    register,
    logout,
    refreshSession,
    authFetch,
  }), [accessToken, authFetch, login, logout, refreshSession, refreshToken, register, status, user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
