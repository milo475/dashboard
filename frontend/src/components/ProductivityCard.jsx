import { useMemo } from 'react'
import { Card, StateBlock } from './Card.jsx'
import { Sparkline } from './Sparkline.jsx'
import { usePolling } from '../api.js'
import { ACCENT, CATEGORY, DOWN, UP, WARN } from '../theme.js'

const ORDER = ['productive', 'neutral', 'leisure']

function fmtMinutes(minutes) {
  if (!minutes) return '0m'
  const total = Math.round(minutes)
  if (total === 0) return '<1m'
  const h = Math.floor(total / 60)
  const m = total % 60
  if (h === 0) return `${m}m`
  return m === 0 ? `${h}h` : `${h}h ${m}m`
}

function scoreColor(score) {
  if (score == null) return ACCENT
  if (score >= 70) return UP
  if (score >= 40) return WARN
  return DOWN
}

export function ProductivityCard() {
  const { data, error, loading } = usePolling('/api/productivity', 60_000)

  const today = data?.today
  const trend = useMemo(
    // Days with no recorded activity have no score; a flat 0 would read as a
    // terrible day rather than an absent one, so carry the last known value.
    () => {
      const daily = data?.daily ?? []
      let last = null
      return daily
        .map((day) => {
          if (day.score != null) last = day.score
          return last
        })
        .filter((value) => value != null)
    },
    [data],
  )

  let body
  if (loading && !data) {
    body = <StateBlock kind="loading" title="Scoring your day…" />
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
        detail={data?.error ?? 'ActivityWatch is not reachable.'}
        hint={data?.hint ?? 'Start ActivityWatch, then this card fills in.'}
      />
    )
  } else if (!today || today.total_minutes === 0) {
    body = (
      <StateBlock
        kind="empty"
        title="Nothing tracked today"
        detail="ActivityWatch has not recorded any window time yet today."
        hint="The first events appear within a minute of using the machine."
      />
    )
  } else {
    const total = ORDER.reduce((sum, key) => sum + (today[`${key}_minutes`] || 0), 0) || 1
    const color = scoreColor(today.score)
    body = (
      <div className="prod">
        <div className="prod-head">
          <div className="prod-score" style={{ color }}>
            {today.score == null ? '—' : `${Math.round(today.score)}`}
            <span className="prod-pct">%</span>
          </div>
          <div className="prod-trend">
            <span className="prod-trend-label">7-day trend</span>
            <Sparkline points={trend} color={color} width={110} height={30} fill />
          </div>
        </div>

        <div className="prod-bar" role="img" aria-label="Time split by category">
          {ORDER.map((key) => {
            const minutes = today[`${key}_minutes`] || 0
            if (!minutes) return null
            return (
              <span
                key={key}
                className="prod-seg"
                style={{ width: `${(minutes / total) * 100}%`, background: CATEGORY[key] }}
                title={`${key}: ${fmtMinutes(minutes)}`}
              />
            )
          })}
        </div>

        <ul className="prod-legend">
          {ORDER.map((key) => (
            <li key={key}>
              <span className="swatch" style={{ background: CATEGORY[key] }} />
              <span className="prod-legend-name">{key}</span>
              <span className="prod-legend-value">{fmtMinutes(today[`${key}_minutes`])}</span>
            </li>
          ))}
        </ul>

        {data.top?.length ? (
          <ul className="prod-top">
            {data.top.map((row) => (
              <li key={`${row.app}-${row.category}`}>
                <span className="swatch" style={{ background: CATEGORY[row.category] }} />
                <span className="prod-top-app">{row.app}</span>
                <span className="prod-top-value">{fmtMinutes(row.minutes)}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    )
  }

  return (
    <Card
      title="Productivity"
      subtitle={
        data?.available && today
          ? `${fmtMinutes(today.total_minutes)} tracked${data.rules_error ? ' · default rules' : ''}${data.stale ? ' · cached' : ''}`
          : 'productive vs leisure'
      }
      className="card-productivity"
    >
      {body}
    </Card>
  )
}
