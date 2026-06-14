import type { AppProps } from 'next/app'
import { useRouter } from 'next/router'
import { useEffect, useState } from 'react'
import '../styles/globals.css'
import { useAuth } from '../lib/auth-client'
import { AuthProvider } from '../lib/auth-client'

const AUTH_DISABLED = process.env.NEXT_PUBLIC_DISABLE_AUTH === '1'
const PUBLIC_PAGES = ['/', '/login', '/register']

function AppContent({ Component, pageProps }: AppProps) {
  const router = useRouter()
  const { status } = useAuth()
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    try {
      const existing = document.documentElement.getAttribute('data-theme')
      if (!existing) {
        document.documentElement.setAttribute('data-theme', 'light')
      }
    } catch (e) {}
  }, [])

  useEffect(() => {
    if (status === 'loading') return

    const isPublicPage = PUBLIC_PAGES.includes(router.pathname)

    if (status === 'unauthenticated' && !isPublicPage) {
      void router.push('/login')
    } else if (status === 'authenticated' && isPublicPage) {
      void router.push('/workspace')
    } else {
      setIsReady(true)
    }
  }, [status, router])

  if (!isReady) {
    return null
  }

  return <Component {...pageProps} />
}

export default function App(props: AppProps) {
  return (
    <AuthProvider>
      <AppContent {...props} />
    </AuthProvider>
  )
}