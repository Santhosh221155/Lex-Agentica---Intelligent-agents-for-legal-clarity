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

async function refreshSession(refreshToken: string) {
  return refreshRequest(refreshToken)
}

async function proxyResponse(res: NextApiResponse, response: Response) {
  res.status(response.status)
  const contentType = response.headers.get('content-type')
  if (contentType) {
    res.setHeader('Content-Type', contentType)
  }

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

  const chunks: Uint8Array[] = []
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    if (value) {
      chunks.push(value)
    }
  }

  if (chunks.length > 0) {
    res.send(Buffer.concat(chunks))
    return
  }

  res.end()
}

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'method_not_allowed' })
    return
  }

  let accessToken = readRequestAccessToken(req)
  const refreshToken = readCookieFromHeader(req.headers.cookie, REFRESH_TOKEN_COOKIE)

  if (!AUTH_DISABLED && !accessToken && !refreshToken) {
    res.status(401).json({ error: 'unauthenticated', detail: 'Sign in at /login or set DISABLE_AUTH=1 for local dev.' })
    return
  }

  const forwardHeaders: Record<string, string> = {}
  if (req.headers['content-type']) {
    forwardHeaders['content-type'] = req.headers['content-type']
  }
  if (accessToken) {
    forwardHeaders.authorization = `Bearer ${accessToken}`
  }

  const backendUrl = `${BACKEND_URL}/api/ingest/file?${new URLSearchParams(req.query as Record<string, string>).toString()}`
  let backendResponse = await (fetch as any)(backendUrl, {
    method: 'POST',
    headers: forwardHeaders,
    body: req as any,
    duplex: 'half' as any,
  })

  if (backendResponse.status === 401 && refreshToken) {
    try {
      const refreshed = await refreshSession(refreshToken)
      accessToken = refreshed.access_token
      setSessionCookies(res, refreshed.access_token, refreshed.refresh_token)
      forwardHeaders.authorization = `Bearer ${accessToken}`
      backendResponse = await (fetch as any)(backendUrl, {
        method: 'POST',
        headers: forwardHeaders,
        body: req as any,
        duplex: 'half' as any,
      })
    } catch {
      res.status(401).json({ error: 'unauthenticated' })
      return
    }
  }

  await proxyResponse(res, backendResponse)
}

export const config = {
  api: {
    bodyParser: false,
  },
}