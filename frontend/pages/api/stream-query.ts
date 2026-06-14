import type { NextApiRequest, NextApiResponse } from 'next'
import {
  BACKEND_URL,
  ACCESS_TOKEN_COOKIE,
  AUTH_DISABLED,
  REFRESH_TOKEN_COOKIE,
  refreshRequest,
  readRequestAccessToken,
  readCookieFromHeader,
} from '../../lib/auth'

function setSessionCookies(res: NextApiResponse, accessToken: string, refreshToken: string) {
  res.setHeader('Set-Cookie', [
    `${ACCESS_TOKEN_COOKIE}=${encodeURIComponent(accessToken)}; Path=/; SameSite=Lax`,
    `${REFRESH_TOKEN_COOKIE}=${encodeURIComponent(refreshToken)}; Path=/; SameSite=Lax`,
  ])
}

async function getBackendResponse(query: string, accessToken: string | null) {
  return fetch(`${BACKEND_URL}/api/stream-query?q=${encodeURIComponent(query)}`, {
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
  })
}

async function refreshSession(refreshToken: string) {
  return refreshRequest(refreshToken)
}

async function proxyStream(res: NextApiResponse, response: Response) {
  res.status(response.status)
  res.setHeader('Content-Type', response.headers.get('content-type') || 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache, no-transform')
  res.setHeader('Connection', 'keep-alive')
  res.setHeader('X-Accel-Buffering', 'no')

  if (!response.body) {
    const text = await response.text()
    res.send(text)
    return
  }

  const reader = response.body.getReader()
  const cleanup = () => {
    try {
      void reader.cancel()
    } catch {
      // noop
    }
  }
  res.on('close', cleanup)
  res.on('finish', cleanup)

  const decoder = new TextDecoder()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    res.write(decoder.decode(value, { stream: true }))
  }
  res.end()
}

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'GET') {
    res.status(405).json({ error: 'method_not_allowed' })
    return
  }

  const query = typeof req.query.q === 'string' ? req.query.q : ''
  if (!query.trim()) {
    res.status(400).json({ error: 'missing_query' })
    return
  }

  let accessToken = readRequestAccessToken(req)
  const refreshToken = readCookieFromHeader(req.headers.cookie, REFRESH_TOKEN_COOKIE)

  if (!AUTH_DISABLED && !accessToken && !refreshToken) {
    res.status(401).json({ error: 'unauthenticated', detail: 'Sign in at /login or set DISABLE_AUTH=1 for local dev.' })
    return
  }

  let backendResponse = await getBackendResponse(query, accessToken)
  if (backendResponse.status === 401 && refreshToken) {
    try {
      const refreshed = await refreshSession(refreshToken)
      accessToken = refreshed.access_token
      setSessionCookies(res, refreshed.access_token, refreshed.refresh_token)
      backendResponse = await getBackendResponse(query, accessToken)
    } catch {
      res.status(401).json({ error: 'unauthenticated' })
      return
    }
  }

  if (!backendResponse.ok && backendResponse.headers.get('content-type')?.includes('application/json')) {
    const payload = await backendResponse.text()
    res.status(backendResponse.status).send(payload)
    return
  }

  await proxyStream(res, backendResponse)
}

export const config = {
  api: {
    bodyParser: false,
  },
}
