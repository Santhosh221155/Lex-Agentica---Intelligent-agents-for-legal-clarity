import { useEffect, useState } from 'react'
import { useRouter } from 'next/router'
import { useAuth } from '../lib/auth-client'
import Link from 'next/link'

export default function RegisterPage() {
  const router = useRouter()
  const { status, register } = useAuth()
  
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (status === 'authenticated') {
      void router.replace('/workspace')
    }
  }, [status, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    
    try {
      await register(username, email, password)
      void router.push('/login')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  if (status === 'loading' || status === 'authenticated') {
    return null
  }

  return (
    <div style={pageWrap}>
      <div style={cardStyle}>
        {/* Header */}
        <div style={{ marginBottom: 24 }}>
          <h1 style={heading}>Agentic RAG</h1>
          <p style={subheading}>Create your account</p>
        </div>

        {/* Error Message */}
        {error && (
          <div style={errorBox}>
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Username */}
          <div>
            <label htmlFor="username" style={labelStyle}>
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={inputStyle}
              placeholder="username"
              required
              minLength={3}
              disabled={loading}
            />
          </div>

          {/* Email */}
          <div>
            <label htmlFor="email" style={labelStyle}>
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
              placeholder="you@example.com"
              required
              disabled={loading}
            />
          </div>

          {/* Password */}
          <div>
            <label htmlFor="password" style={labelStyle}>
              Password
            </label>
            <div style={{ position: 'relative' }}>
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={inputStyle}
                placeholder="••••••••"
                required
                minLength={8}
                disabled={loading}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={toggleBtn}
                tabIndex={-1}
              >
                {showPassword ? (
                  <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                ) : (
                  <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-4.803m5.596-3.856a3.375 3.375 0 11-4.753 4.753M9.001 9l.622.638m0 0a3.36 3.36 0 015.946 0l.625-.624m-.624.624a3.36 3.36 0 010 5.946m-6.217-6.217L5.007 5.007m3.994 3.994L9.001 9m0 0l6-6" />
                  </svg>
                )}
              </button>
            </div>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>Minimum 8 characters</p>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            style={submitBtn}
          >
            {loading ? 'Creating account...' : 'Sign up'}
          </button>
        </form>

        {/* Login Link */}
        <div style={{ marginTop: 16, textAlign: 'center', fontSize: 14 }}>
          <span style={{ color: 'var(--text-secondary)' }}>Already have an account? </span>
          <Link href="/login" style={{ color: 'var(--primary)', fontWeight: 600 }}>Sign in</Link>
        </div>
      </div>
    </div>
  )
}

const pageWrap: React.CSSProperties = {
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'var(--bg)',
  padding: '0 16px',
}

const cardStyle: React.CSSProperties = {
  width: '100%',
  maxWidth: 400,
  background: 'var(--panel)',
  borderRadius: 16,
  boxShadow: 'var(--shadow-md)',
  border: '1px solid var(--border)',
  padding: 24,
}

const heading: React.CSSProperties = {
  fontSize: 24,
  fontWeight: 700,
  textAlign: 'center',
  color: 'var(--text-primary)',
  margin: 0,
}

const subheading: React.CSSProperties = {
  textAlign: 'center',
  color: 'var(--text-muted)',
  fontSize: 14,
  marginTop: 4,
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 14,
  fontWeight: 500,
  color: 'var(--text-secondary)',
  marginBottom: 6,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  border: '1px solid var(--border)',
  borderRadius: 8,
  background: 'var(--bg-soft)',
  color: 'var(--text-primary)',
  fontSize: 14,
  outline: 'none',
}

const toggleBtn: React.CSSProperties = {
  position: 'absolute',
  right: 12,
  top: '50%',
  transform: 'translateY(-50%)',
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  color: 'var(--text-muted)',
  padding: 0,
  display: 'flex',
  alignItems: 'center',
}

const submitBtn: React.CSSProperties = {
  width: '100%',
  background: 'var(--primary)',
  color: 'white',
  fontWeight: 500,
  padding: '10px 16px',
  borderRadius: 8,
  border: 'none',
  cursor: 'pointer',
  fontSize: 14,
  transition: 'background 200ms ease',
}

const errorBox: React.CSSProperties = {
  marginBottom: 16,
  padding: 12,
  background: 'color-mix(in srgb, var(--danger) 10%, var(--panel))',
  border: '1px solid color-mix(in srgb, var(--danger) 20%, transparent)',
  borderRadius: 8,
  color: 'var(--danger)',
  fontSize: 14,
}
