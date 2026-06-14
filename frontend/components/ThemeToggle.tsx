import { useEffect, useState } from 'react'

export default function ThemeToggle() {
  const [theme, setTheme] = useState<string | null>(null)

  useEffect(() => {
    try {
      const stored = localStorage.getItem('theme')
      const initial = stored || 'light'
      setTheme(initial)
      document.documentElement.setAttribute('data-theme', initial)
    } catch (e) {
      // noop
    }
  }, [])

  function toggle() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    try {
      document.documentElement.setAttribute('data-theme', next)
      localStorage.setItem('theme', next)
    } catch (e) {}
  }

  return (
    <button
      onClick={toggle}
      aria-label="Toggle theme"
      title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 40,
        height: 40,
        borderRadius: 10,
        border: '1px solid var(--border)',
        background: 'var(--panel)',
        color: 'var(--text)',
        cursor: 'pointer',
        boxShadow: 'var(--shadow)',
      }}
    >
      {theme === 'dark' ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" fill="var(--text)" />
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 3v2M12 19v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42M12 7a5 5 0 100 10 5 5 0 000-10z" stroke="var(--text)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )}
    </button>
  )
}
