import { useCallback, useEffect, useState } from 'react'
import { Clock } from './components/Clock.jsx'
import { UsageCard } from './components/UsageCard.jsx'
import { StocksCard } from './components/StocksCard.jsx'
import { NewsCard } from './components/NewsCard.jsx'

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
      <button
        type="button"
        className="claude-button"
        onClick={launch}
        disabled={status?.kind === 'pending'}
      >
        Claude
      </button>
      {status ? (
        <span className={`launch-status launch-${status.kind}`} role="status">
          {status.message}
        </span>
      ) : null}
    </div>
  )
}

export default function App() {
  return (
    <div className="shell">
      <header className="topbar">
        <Clock />
        <div className="topbar-right">
          <ClaudeButton />
        </div>
      </header>
      <main className="grid">
        <div className="col-left">
          <UsageCard />
        </div>
        <div className="col-right">
          <StocksCard />
          <NewsCard />
        </div>
      </main>
    </div>
  )
}
