import { useCallback, useEffect, useMemo, useState } from 'react'
import { Card } from '../Card.jsx'
import { postJson, usePolling } from '../../api.js'

const DOW = ['M', 'T', 'W', 'T', 'F', 'S', 'S'] // Monday first, like the schedule

/* Cells for a Monday-first month grid: leading blanks, then 1..n. */
function monthCells(year, month) {
  const first = new Date(year, month, 1)
  const offset = (first.getDay() + 6) % 7
  const count = new Date(year, month + 1, 0).getDate()
  const cells = Array(offset).fill(null)
  for (let day = 1; day <= count; day += 1) cells.push(day)
  while (cells.length % 7) cells.push(null)
  return cells
}

/* "10:00–12:00" → [600, 720]; anything else (All day…) → null. */
function parseRange(text) {
  const match = /^\s*(\d{1,2})[:.](\d{2})\s*(?:[–—-]|to)\s*(\d{1,2})[:.](\d{2})/.exec(text || '')
  if (!match) return null
  return [Number(match[1]) * 60 + Number(match[2]), Number(match[3]) * 60 + Number(match[4])]
}

function MonthCalendar({ now }) {
  const cells = useMemo(() => monthCells(now.getFullYear(), now.getMonth()), [now])
  return (
    <div className="tile tile-cal">
      <div className="tile-label">
        <span>{now.toLocaleDateString(undefined, { month: 'long' })}</span>
        <span className="tile-label-soft">{now.getFullYear()}</span>
      </div>
      <div className="cal-grid" role="grid" aria-label="This month">
        {DOW.map((label, index) => (
          <span key={`dow-${index}`} className="cal-dow" aria-hidden="true">
            {label}
          </span>
        ))}
        {cells.map((day, index) => (
          <span
            key={`d-${index}`}
            className={`cal-day${day === now.getDate() ? ' today' : ''}${day == null ? ' empty' : ''}`}
            aria-current={day === now.getDate() ? 'date' : undefined}
          >
            {day ?? ''}
          </span>
        ))}
      </div>
    </div>
  )
}

function Routine() {
  const { data, error, reload } = usePolling('/api/routine', 60_000)
  const [local, setLocal] = useState(null)
  const [draft, setDraft] = useState('')
  const state = local ?? (data?.available ? data : null)

  useEffect(() => {
    if (data?.available) setLocal(null)
  }, [data])

  const apply = useCallback(
    async (optimistic, body) => {
      setLocal(optimistic)
      try {
        const next = await postJson('/api/routine', body)
        if (next?.available) setLocal(next)
        else reload()
      } catch {
        reload()
      }
    },
    [reload],
  )

  const toggle = (item) =>
    apply(
      { ...state, items: state.items.map((i) => (i.id === item.id ? { ...i, done: !i.done } : i)) },
      { toggle: item.id, done: !item.done },
    )

  const remove = (item) => {
    const items = state.items.filter((i) => i.id !== item.id)
    apply({ ...state, items }, { items })
  }

  const add = (event) => {
    event.preventDefault()
    const text = draft.trim()
    if (!text || !state) return
    setDraft('')
    const items = [...state.items, { id: `tmp-${Date.now()}`, text, done: false }]
    apply({ ...state, items }, { items })
  }

  const items = state?.items ?? []
  const done = items.filter((i) => i.done).length
  const full = items.length >= (state?.max_items ?? 8)

  return (
    <div className="tile tile-routine">
      <div className="tile-label">
        <span>morning</span>
        <span className="tile-label-soft">
          {state ? `${done}/${items.length}` : error ? 'offline' : '…'}
        </span>
      </div>
      <ul className="routine-list">
        {items.map((item) => (
          <li key={item.id} className={item.done ? 'done' : ''}>
            <button
              type="button"
              className="routine-toggle"
              aria-pressed={item.done}
              onClick={() => toggle(item)}
            >
              <span className="routine-box" aria-hidden="true">{item.done ? '✓' : ''}</span>
              <span className="routine-text">{item.text}</span>
            </button>
            <button
              type="button"
              className="routine-remove"
              aria-label={`Remove ${item.text}`}
              onClick={() => remove(item)}
            >
              ×
            </button>
          </li>
        ))}
        {state && items.length === 0 ? <li className="routine-empty">No routine yet.</li> : null}
      </ul>
      <form className="routine-add" onSubmit={add}>
        <input
          type="text"
          value={draft}
          maxLength={120}
          disabled={!state || full}
          placeholder={full ? 'Routine is full' : 'Add a step…'}
          aria-label="Add a routine step"
          onChange={(event) => setDraft(event.target.value)}
        />
        <button type="submit" disabled={!state || full || !draft.trim()}>
          add
        </button>
      </form>
    </div>
  )
}

/* The tile has room for three blocks, so it shows what is still ahead: the
 * block running now (highlighted) and the next ones. Finished blocks drop off
 * as the day goes on; "All day" style blocks never expire. */
function DayTile({ now, blocks }) {
  const minutes = now.getHours() * 60 + now.getMinutes()
  const ahead = blocks.filter((block) => {
    const range = parseRange(block.time)
    return !range || range[1] > minutes
  })
  const shown = ahead.slice(0, 3)
  return (
    <div className="tile tile-day">
      <div className="day-name">{now.toLocaleDateString(undefined, { weekday: 'long' })}</div>
      <div className="day-number">{now.getDate()}</div>
      <ul className="agenda" aria-label="Today's schedule">
        {shown.map((block) => {
          const range = parseRange(block.time)
          const live = range && minutes >= range[0] && minutes < range[1]
          return (
            <li key={block.id} className={live ? 'now' : ''}>
              <span className="agenda-time">{block.time}</span>
              <span className="agenda-title">{block.title}</span>
              {block.note ? <span className="agenda-note">{block.note}</span> : null}
            </li>
          )
        })}
        {blocks.length === 0 ? <li className="agenda-empty">Nothing planned today.</li> : null}
        {blocks.length > 0 && ahead.length === 0 ? (
          <li className="agenda-empty">All done for today ✓</li>
        ) : null}
        {ahead.length > shown.length ? (
          <li className="agenda-more">+{ahead.length - shown.length} more</li>
        ) : null}
      </ul>
    </div>
  )
}

function PhotoTile({ photo }) {
  if (!photo) {
    return (
      <div className="tile tile-photo placeholder">
        <span>
          your photo here
          <br />
          backend/data/photos
        </span>
      </div>
    )
  }
  return (
    <div className="tile tile-photo">
      <img src={photo.url} alt="" />
    </div>
  )
}

export function TodayCard({ blocks, photo }) {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <Card
      title="Today"
      subtitle={now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}
      className="card-today"
    >
      <div className="today-grid">
        <MonthCalendar now={now} />
        <Routine />
        <PhotoTile photo={photo} />
        <DayTile now={now} blocks={blocks} />
      </div>
    </Card>
  )
}
