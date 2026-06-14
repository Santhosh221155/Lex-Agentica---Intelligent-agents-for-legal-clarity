import { useEffect } from 'react'
import { useRouter } from 'next/router'
import Link from 'next/link'
import { useAuth } from '../lib/auth-client'

export default function Home() {
  const router = useRouter()
  const { status } = useAuth()

  useEffect(() => {
    if (status === 'authenticated') {
      void router.replace('/workspace')
    }
  }, [status, router])

  if (status === 'authenticated' || status === 'loading') {
    return null
  }

  return (
    <div style={page}>
      <div style={center}>
        <h1 style={title}>Agentic RAG</h1>
        <p style={subtitle}>Intelligent document analysis and retrieval</p>
        <div style={actions}>
          <Link href="/login" style={signInBtn}>
            Sign In
          </Link>
          <Link href="/register" style={signUpBtn}>
            Sign Up
          </Link>
        </div>
      </div>
    </div>
  )
}

const page: React.CSSProperties = {
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'var(--bg)',
}

const center: React.CSSProperties = {
  textAlign: 'center',
  padding: '0 24px',
}

const title: React.CSSProperties = {
  fontSize: 'clamp(2.5rem, 6vw, 4rem)',
  fontWeight: 800,
  color: 'var(--text-primary)',
  margin: 0,
  letterSpacing: '-0.03em',
}

const subtitle: React.CSSProperties = {
  color: 'var(--text-muted)',
  fontSize: 18,
  marginTop: 12,
  marginBottom: 40,
}

const actions: React.CSSProperties = {
  display: 'flex',
  gap: 12,
  justifyContent: 'center',
  flexWrap: 'wrap',
}

const signInBtn: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '12px 32px',
  borderRadius: 10,
  background: 'var(--primary)',
  color: '#fff',
  fontWeight: 600,
  fontSize: 15,
  textDecoration: 'none',
  border: 'none',
  cursor: 'pointer',
  transition: 'background 180ms ease',
  minWidth: 140,
}

const signUpBtn: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '12px 32px',
  borderRadius: 10,
  background: 'transparent',
  color: 'var(--text-primary)',
  fontWeight: 600,
  fontSize: 15,
  textDecoration: 'none',
  border: '1px solid var(--border)',
  cursor: 'pointer',
  transition: 'border-color 180ms ease, background 180ms ease',
  minWidth: 140,
}
