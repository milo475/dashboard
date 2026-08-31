import { useEffect, useState } from 'react'
import { Card, StateBlock } from './Card.jsx'
import { usePolling } from '../api.js'

const KIND_CLASS = {
  push: 'ev-push',
  pr: 'ev-pr',
  issue: 'ev-issue',
  comment: 'ev-issue',
  review: 'ev-pr',
  create: 'ev-create',
  release: 'ev-create',
  fork: 'ev-create',
}

/* Relative time is computed here, not on the backend, so "2h ago" keeps
 * counting between the 5-minute refreshes instead of freezing. */
function timeAgo(iso, now) {
  if (!iso) return '—'
  const seconds = (now - new Date(iso).getTime()) / 1000
  if (Number.isNaN(seconds)) return '—'
  if (seconds < 60) return 'now'
  const minutes = seconds / 60
  if (minutes < 60) return `${Math.floor(minutes)}m ago`
  const hours = minutes / 60
  if (hours < 24) return `${Math.floor(hours)}h ago`
  const days = hours / 24
  if (days < 30) return `${Math.floor(days)}d ago`
  const months = days / 30
  if (months < 12) return `${Math.floor(months)}mo ago`
  return `${Math.floor(months / 12)}y ago`
}

export function GithubCard() {
  const { data, error, loading } = usePolling('/api/github', 300_000)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])

  let body
  if (loading && !data) {
    body = <StateBlock kind="loading" title="Loading activity…" />
  } else if (error) {
    body = (
      <StateBlock
        kind="error"
        title="No data"
        detail={`Backend unreachable: ${error}`}
        hint="Is dashboard-backend.service running?"
      />
    )
  } else if (!data?.available) {
    body = (
      <StateBlock
        kind="error"
        title="No data"
        detail={data?.error ?? 'GitHub could not be reached.'}
        hint={data?.hint ?? 'Check the internet connection.'}
      />
    )
  } else {
    // "pushes" means GitHub gave us no commit counts, so say what the number
    // really is instead of labelling pushes as commits.
    const isCommits = data.commits_source !== 'pushes'
    body = (
      <div className="gh">
        <div className="gh-today">
          <span className="gh-count">{data.commits_today}</span>
          <span className="gh-count-label">
            {isCommits ? 'commits' : 'pushes'} today
          </span>
        </div>

        <ul className="gh-repos">
          {data.repos.map((repo) => (
            <li key={repo.name}>
              <a href={repo.url} target="_blank" rel="noreferrer noopener">
                <span className="gh-repo-name">{repo.name}</span>
                <span className="gh-repo-meta">
                  {repo.language ? <span className="gh-lang">{repo.language}</span> : null}
                  <span className="gh-ago">{timeAgo(repo.pushed_at, now)}</span>
                </span>
              </a>
            </li>
          ))}
          {data.repos.length === 0 ? <li className="gh-empty">No public repos.</li> : null}
        </ul>

        <ul className="gh-events">
          {data.events.map((event) => (
            <li key={event.id}>
              <a href={event.url} target="_blank" rel="noreferrer noopener">
                <span className={`gh-kind ${KIND_CLASS[event.kind] ?? ''}`}>{event.kind}</span>
                <span className="gh-event-text">
                  <span className="gh-event-repo">{event.repo}</span> {event.action}
                  {event.detail ? <span className="gh-event-detail"> · {event.detail}</span> : null}
                </span>
                <span className="gh-ago">{timeAgo(event.at, now)}</span>
              </a>
            </li>
          ))}
          {data.events.length === 0 ? (
            <li className="gh-empty">No public activity in the last 90 days.</li>
          ) : null}
        </ul>
      </div>
    )
  }

  return (
    <Card
      title="GitHub"
      subtitle={
        data?.available
          ? `${data.user}${data.authenticated ? '' : ' · anon'}${data.stale ? ' · cached' : ''}`
          : 'github'
      }
      className="card-github"
    >
      {body}
    </Card>
  )
}
