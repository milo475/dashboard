import { useState } from 'react'
import { Card, StateBlock } from '../Card.jsx'

const DAYS = [
  ['mon', 'M', 'Monday'],
  ['tue', 'T', 'Tuesday'],
  ['wed', 'W', 'Wednesday'],
  ['thu', 'TH', 'Thursday'],
  ['fri', 'F', 'Friday'],
  ['sat', 'SA', 'Saturday'],
  ['sun', 'SU', 'Sunday'],
]

export function ScheduleCard({ state, loading, error, unavailable, saveError, onChange }) {
  const [draft, setDraft] = useState({ day: null, time: '', title: '', note: '' })
  const day = draft.day ?? state?.today ?? 'mon'
  const max = state?.max_blocks ?? 8
  const full = state ? (state.days[day] ?? []).length >= max : true

  const submit = (event) => {
    event.preventDefault()
    const title = draft.title.trim()
    if (!title || !state || full) return
    const block = {
      id: `tmp-${Date.now()}`,
      time: draft.time.trim() || 'All day',
      title,
      note: draft.note.trim(),
    }
    onChange({ ...state.days, [day]: [...(state.days[day] ?? []), block] })
    setDraft((d) => ({ ...d, time: '', title: '', note: '' }))
  }

  const remove = (key, id) =>
    onChange({ ...state.days, [key]: (state.days[key] ?? []).filter((b) => b.id !== id) })

  let body
  if (loading) {
    body = <StateBlock kind="loading" title="Loading the week…" />
  } else if (error) {
    body = (
      <StateBlock
        kind="error"
        title="No data"
        detail={`Backend unreachable: ${error}`}
        hint="Is dashboard-backend.service running?"
      />
    )
  } else if (!state) {
    body = (
      <StateBlock
        kind="error"
        title="No data"
        detail={unavailable?.error ?? 'The schedule could not be loaded.'}
        hint={unavailable?.hint ?? 'Check that backend/data/ is writable.'}
      />
    )
  } else {
    body = (
      <div className="schedule">
        <div className="week">
          {DAYS.map(([key, short, long]) => {
            const blocks = state.days[key] ?? []
            return (
              <div key={key} className={`week-day${key === state.today ? ' today' : ''}`}>
                <div className="week-head" title={long}>
                  {short}
                </div>
                <div className="week-col">
                  {blocks.map((block) => (
                    <div key={block.id} className="block">
                      <span className="block-time">{block.time}</span>
                      <span className="block-title">{block.title}</span>
                      {block.note ? <span className="block-note">{block.note}</span> : null}
                      <button
                        type="button"
                        className="block-remove"
                        aria-label={`Remove ${block.title} on ${long}`}
                        onClick={() => remove(key, block.id)}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                  {blocks.length === 0 ? <div className="block block-empty">—</div> : null}
                </div>
              </div>
            )
          })}
        </div>
        <form className="schedule-add" onSubmit={submit}>
          <select
            value={day}
            aria-label="Day"
            onChange={(event) => setDraft((d) => ({ ...d, day: event.target.value }))}
          >
            {DAYS.map(([key, , long]) => (
              <option key={key} value={key}>
                {long}
              </option>
            ))}
          </select>
          <input
            type="text"
            className="schedule-time"
            value={draft.time}
            maxLength={24}
            placeholder="10:00–12:00"
            aria-label="Time"
            onChange={(event) => setDraft((d) => ({ ...d, time: event.target.value }))}
          />
          <input
            type="text"
            value={draft.title}
            maxLength={60}
            disabled={full}
            placeholder={full ? `${max} blocks max on that day` : 'What is the plan?'}
            aria-label="Title"
            onChange={(event) => setDraft((d) => ({ ...d, title: event.target.value }))}
          />
          <input
            type="text"
            className="schedule-note"
            value={draft.note}
            maxLength={60}
            placeholder="room · teacher (optional)"
            aria-label="Note"
            onChange={(event) => setDraft((d) => ({ ...d, note: event.target.value }))}
          />
          <button type="submit" disabled={full || !draft.title.trim()}>
            add
          </button>
        </form>
        {saveError ? <div className="schedule-error">{saveError}</div> : null}
      </div>
    )
  }

  const total = state ? DAYS.reduce((sum, [key]) => sum + (state.days[key]?.length ?? 0), 0) : 0
  return (
    <Card
      title="My schedule"
      subtitle={state ? `${total} blocks this week` : 'monday → sunday'}
      className="card-schedule"
    >
      {body}
    </Card>
  )
}
