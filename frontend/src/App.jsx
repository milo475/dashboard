import { useCallback, useEffect, useState } from 'react'
import { Clock } from './components/Clock.jsx'
import { ThemeProvider, useTheme } from './ThemeContext.jsx'
import { Board } from './pages/Board.jsx'
import { Planner } from './pages/Planner.jsx'

const PAGE_KEY = 'dashboard.page.v1'
const PAGES = [
  { id: 'planner', label: 'Planner', key: '1' },
  { id: 'board', label: 'Board', key: '2' },
]

/* ?page=board in the URL wins, then the last page used in this browser. */
function initialPage() {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('page')
    if (PAGES.some((p) => p.id === fromUrl)) return fromUrl
    const stored = localStorage.getItem(PAGE_KEY)
    if (PAGES.some((p) => p.id === stored)) return stored
  } catch {
    /* no storage - fall through */
  }
  return 'planner'
}

const typing = (target) =>
  target &&
  (target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.tagName === 'SELECT' ||
    target.isContentEditable)

function ClaudeButton() {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    if (!status || status.kind === 'pending') return undefined
    const id = setTimeout(() => setStatus(null), 6000)
    return () => clearTimeout(id)
  }, [status])

  const launch = useCallback(async () => {
    setStatus({ kind: 'pending', message: 'starting…' })
    try {
      const res = await fetch('/api/launch/claude', { method: 'POST' })
      const body = await res.json().catch(() => ({}))
      setStatus(
        res.ok && body.ok
          ? { kind: 'ok', message: 'launched' }
          : { kind: 'error', message: body.error ?? `failed (HTTP ${res.status})` },
      )
    } catch (err) {
      setStatus({ kind: 'error', message: err.message || 'request failed' })
    }
  }, [])

  return (
    <div className="launch">
      {status ? (
        <span className={`launch-status launch-${status.kind}`} role="status">
          {status.message}
        </span>
      ) : null}
      <button
        type="button"
        className="claude-button"
        onClick={launch}
        disabled={status?.kind === 'pending'}
      >
        Claude
      </button>
    </div>
  )
}

function PageTabs({ page, onChange }) {
  return (
    <div className="tabs" role="tablist" aria-label="Dashboard page">
      {PAGES.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={page === item.id}
          className={page === item.id ? 'on' : ''}
          onClick={() => onChange(item.id)}
        >
          {item.label}
          <kbd aria-hidden="true">{item.key}</kbd>
        </button>
      ))}
    </div>
  )
}

function ThemeSwitch() {
  const { theme, toggle } = useTheme()
  const next = theme === 'noir' ? 'cream' : 'noir'
  return (
    <button
      type="button"
      className="theme-switch"
      onClick={toggle}
      aria-label={`Switch to the ${next} theme`}
      title={`Theme: ${theme} (press t)`}
    >
      <span className="theme-dot" aria-hidden="true" />
      {theme}
    </button>
  )
}

function Shell() {
  const [page, setPage] = useState(initialPage)
  const { toggle } = useTheme()

  useEffect(() => {
    try {
      localStorage.setItem(PAGE_KEY, page)
    } catch {
      /* cosmetic */
    }
  }, [page])

  // 1 / 2 flip pages, t flips the theme - unless a field has focus.
  useEffect(() => {
    const onKey = (event) => {
      if (typing(event.target) || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key === '1') setPage('planner')
      else if (event.key === '2') setPage('board')
      else if (event.key === 't' || event.key === 'T') toggle()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggle])

  return (
    <div className={`shell page-${page}`}>
      <header className="topbar">
        <Clock />
        <PageTabs page={page} onChange={setPage} />
        <div className="topbar-right">
          <ThemeSwitch />
          <ClaudeButton />
        </div>
      </header>
      {page === 'board' ? <Board /> : <Planner />}
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <Shell />
    </ThemeProvider>
  )
}
