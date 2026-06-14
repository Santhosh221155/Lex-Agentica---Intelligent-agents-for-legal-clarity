export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
export const AUTH_DISABLED = process.env.NEXT_PUBLIC_DISABLE_AUTH === '1'
export const ACCESS_TOKEN_COOKIE = 'agentic_access_token'
export const REFRESH_TOKEN_COOKIE = 'agentic_refresh_token'
export const ACCESS_TOKEN_STORAGE_KEY = 'agentic_access_token'
export const REFRESH_TOKEN_STORAGE_KEY = 'agentic_refresh_token'

export type AuthUser = {
  id: number | string
  username: string
  email: string
  is_admin?: boolean
  tenant_id?: number | null
  workspace_id?: number | null
  scopes?: string[] | null
}

export type AuthTokens = {
  accessToken: string | null
  refreshToken: string | null
}

export type AuthSession = AuthTokens & {
  user: AuthUser | null
}

function isBrowser() {
  return typeof window !== 'undefined' && typeof document !== 'undefined'
}

function serializeCookie(name: string, value: string, maxAgeSeconds?: number) {
  const encoded = encodeURIComponent(value)
  const agePart = typeof maxAgeSeconds === 'number' ? `; Max-Age=${maxAgeSeconds}` : ''
  return `${name}=${encoded}; Path=/; SameSite=Lax${agePart}`
}

export function readCookie(name: string): string | null {
  if (!isBrowser()) return null
  const prefix = `${name}=`
  const cookies = document.cookie ? document.cookie.split('; ') : []
  const match = cookies.find((item) => item.startsWith(prefix))
  if (!match) return null
  return decodeURIComponent(match.slice(prefix.length))
}

export function readCookieFromHeader(cookieHeader: string | undefined, name: string): string | null {
  if (!cookieHeader) return null
  const prefix = `${name}=`
  const match = cookieHeader.split(';').map((item) => item.trim()).find((item) => item.startsWith(prefix))
  if (!match) return null
  return decodeURIComponent(match.slice(prefix.length))
}

/** Resolve bearer token for Next.js API routes (header, cookie, or query). */
export function readRequestAccessToken(req: {
  headers?: { authorization?: string | string[]; cookie?: string }
  query?: Partial<Record<string, string | string[] | undefined>>
}): string | null {
  const authHeader = req.headers?.authorization
  const headerValue = Array.isArray(authHeader) ? authHeader[0] : authHeader
  if (headerValue?.toLowerCase().startsWith('bearer ')) {
    return headerValue.slice(7).trim() || null
  }

  const cookieToken = readCookieFromHeader(req.headers?.cookie, ACCESS_TOKEN_COOKIE)
  if (cookieToken) return cookieToken

  const queryToken = req.query?.access_token
  const queryValue = Array.isArray(queryToken) ? queryToken[0] : queryToken
  return typeof queryValue === 'string' && queryValue.trim() ? queryValue.trim() : null
}

export function writeCookie(name: string, value: string, maxAgeSeconds = 60 * 60 * 24 * 7) {
  if (!isBrowser()) return
  document.cookie = serializeCookie(name, value, maxAgeSeconds)
}

export function clearCookie(name: string) {
  if (!isBrowser()) return
  document.cookie = serializeCookie(name, '', 0)
}

export function getStoredTokens(): AuthTokens {
  if (!isBrowser()) {
    return { accessToken: null, refreshToken: null }
  }

  const accessToken = readCookie(ACCESS_TOKEN_COOKIE)
  const refreshToken = readCookie(REFRESH_TOKEN_COOKIE)
  return { accessToken, refreshToken }
}

export function persistTokens(tokens: AuthTokens) {
  if (!isBrowser()) return
  if (tokens.accessToken) {
    writeCookie(ACCESS_TOKEN_COOKIE, tokens.accessToken, 60 * 60 * 24 * 7)
  }
  if (tokens.refreshToken) {
    writeCookie(REFRESH_TOKEN_COOKIE, tokens.refreshToken, 60 * 60 * 24 * 7)
  }
}

export function clearTokens() {
  if (!isBrowser()) return
  clearCookie(ACCESS_TOKEN_COOKIE)
  clearCookie(REFRESH_TOKEN_COOKIE)
}

export function authHeaders(accessToken?: string | null): HeadersInit {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {}
}

export async function loginRequest(username: string, password: string) {
  const response = await fetch(`${BACKEND_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    credentials: 'include', // Include cookies in request
  })

  if (!response.ok) {
    const errorText = await response.text()
    try {
      const parsed = JSON.parse(errorText)
      throw new Error(JSON.stringify(parsed))
    } catch (inner) {
      if (inner instanceof Error && inner.message.startsWith('{')) {
        throw inner
      }
      throw new Error(errorText || 'Login failed')
    }
  }

  return response.json() as Promise<{ access_token: string; refresh_token: string }>
}

export async function registerRequest(username: string, email: string, password: string) {
  const response = await fetch(`${BACKEND_URL}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password }),
    credentials: 'include', // Include cookies in request
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || 'Registration failed')
  }

  return response.json()
}

export async function refreshRequest(refreshToken?: string | null) {
  const init: RequestInit = {
    method: 'POST',
    credentials: 'include', // Include cookies in request
  }

  if (refreshToken) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify({ refresh_token: refreshToken })
  }

  const response = await fetch(`${BACKEND_URL}/api/auth/refresh`, init)

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || 'Refresh failed')
  }

  return response.json() as Promise<{ access_token: string; refresh_token: string }>
}

export async function meRequest(accessToken?: string) {
  const response = await fetch(`${BACKEND_URL}/api/auth/me`, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    credentials: 'include', // Include cookies in request
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || 'Unable to load current user')
  }

  return response.json() as Promise<AuthUser>
}

export async function backendFetch(input: RequestInfo | URL, init: RequestInit = {}, accessToken?: string | null) {
  const headers = new Headers(init.headers || {})
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }
  return fetch(input, {
    ...init,
    headers,
  })
}
