import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Card, StateBlock } from './Card.jsx'
import { postJson, usePolling } from '../api.js'

const WORK_SECONDS = 25 * 60
const BREAK_SECONDS = 5 * 60
const TIMER_KEY = 'dashboard.pomodoro.v1'

const mmss = (seconds) => {
  const s = Math.max(0, Math.round(seconds))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

const phaseLength = (phase) => (phase === 'break' ? BREAK_SECONDS : WORK_SECONDS)

/* The timer survives a reload (Vite restarts, an accidental refresh) by storing
 * an absolute deadline rather than a countdown - wall-clock time keeps running
 * whether or not this tab is alive. */
function loadTimer() {
  try {
    const raw = JSON.parse(localStorage.getItem(TIMER_KEY) || 'null')
    if (!raw || (raw.phase !== 'work' && raw.phase !== 'break')) throw new Error('reset')
    if (raw.running && typeof raw.endsAt === 'number') {
      const left = (raw.endsAt - Date.now()) / 1000
      // A deadline that expired while nothing was watching: come back paused at
      // the start of the phase rather than firing a notification hours late.
      if (left <= 0) return { phase: raw.phase, running: false, remaining: phaseLength(raw.phase) }
      return { phase: raw.phase, running: true, endsAt: raw.endsAt, remaining: left }
    }
    return {
      phase: raw.phase,
      running: false,
      remaining: Math.min(phaseLength(raw.phase), Math.max(0, Number(raw.remaining) || 0)),
    }
  } catch {
    return { phase: 'work', running: false, remaining: WORK_SECONDS }
  }
}

function notify(phase) {
  try {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return
    const done = phase === 'work'
    new Notification(done ? 'Pomodoro complete' : 'Break over', {
      body: done ? 'Take a 5 minute break.' : 'Back to it — 25 minutes.',
      tag: 'home-dashboard-pomodoro',
    })
  } catch {
    /* notifications are a nicety; never let one break the timer */
  }
}

function Goals({ state, onChange, disabled }) {
  const [draft, setDraft] = useState('')
  const goals = state?.goals ?? []
  const full = goals.length >= (state?.max_goals ?? 5)

  const submit = (event) => {
    event.preventDefault()
    const text = draft.trim()
    if (!text || full) return
    setDraft('')
    onChange([...goals, { text, done: false }])
  }

  return (
    <div className="goals">
      <div className="goals-head">
        <span>today&rsquo;s goals</span>
        <span className="goals-count">
          {goals.filter((g) => g.done).length}/{goals.length}
        </span>
      </div>
      <ul className="goal-list">
        {goals.map((goal) => (
          <li key={goal.id} className={goal.done ? 'done' : ''}>
            <button
              type="button"
              className="goal-toggle"
              disabled={disabled}
              aria-pressed={goal.done}
              onClick={() =>
                onChange(
                  goals.map((g) => (g.id === goal.id ? { ...g, done: !g.done } : g)),
                )
              }
            >
              <span className="goal-box" aria-hidden="true">{goal.done ? '✓' : ''}</span>
              <span className="goal-text">{goal.text}</span>
            </button>
            <button
              type="button"
              className="goal-remove"
              aria-label={`Remove ${goal.text}`}
              disabled={disabled}
              onClick={() => onChange(goals.filter((g) => g.id !== goal.id))}
            >
              ×
            </button>
          </li>
        ))}
        {goals.length === 0 ? <li className="goal-empty">No goals set for today.</li> : null}
      </ul>
      <form className="goal-add" onSubmit={submit}>
        <input
          type="text"
          value={draft}
          maxLength={120}
          disabled={disabled || full}
          placeholder={full ? `Max ${state?.max_goals ?? 5} goals` : 'Add a goal…'}
          aria-label="Add a goal"
          onChange={(event) => setDraft(event.target.value)}
        />
        <button type="submit" disabled={disabled || full || !draft.trim()}>
          add
        </button>
      </form>
    </div>
  )
}

export function FocusCard() {
  // Poll slowly: this card owns its state, and the poll only reconciles it with
  // the file (and rolls the list over at midnight).
  const { data, error, loading, reload } = usePolling('/api/goals', 60_000)
  const [local, setLocal] = useState(null)
  const [saveError, setSaveError] = useState(null)

  const state = local ?? (data?.available ? data : null)

  const [timer, setTimer] = useState(loadTimer)
  const [flash, setFlash] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const completing = useRef(false)

  useEffect(() => {
    // Adopt the server's list whenever a fresh poll lands, unless a write is
    // still settling (local wins until its own response replaces it).
    if (data?.available) setLocal(null)
  }, [data])

  useEffect(() => {
    try {
      localStorage.setItem(TIMER_KEY, JSON.stringify(timer))
    } catch {
      /* a forgotten timer position is cosmetic */
    }
  }, [timer])

  useEffect(() => {
    if (!timer.running) return undefined
    const id = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(id)
  }, [timer.running])

  const remaining = timer.running
    ? Math.max(0, (timer.endsAt - now) / 1000)
    : timer.remaining

  const finish = useCallback(
    async (phase) => {
      setFlash(true)
      setTimeout(() => setFlash(false), 6000)
      notify(phase)
      const next = phase === 'work' ? 'break' : 'work'
      setTimer({ phase: next, running: false, remaining: phaseLength(next) })
      if (phase !== 'work') return
      try {
        const body = await postJson('/api/pomodoro', { delta: 1 })
        if (body?.available) setLocal(body)
      } catch {
        reload() // the count lives in the file; a failed bump just re-syncs
      }
    },
    [reload],
  )

  useEffect(() => {
    if (!timer.running || remaining > 0 || completing.current) return
    completing.current = true
    finish(timer.phase).finally(() => {
      completing.current = false
    })
  }, [finish, remaining, timer.phase, timer.running])

  const start = () => {
    try {
      if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
        // Chrome only grants this from a user gesture, so ask on the click.
        Notification.requestPermission().catch(() => {})
      }
    } catch {
      /* no Notification API here - the border flash still works */
    }
    setNow(Date.now())
    setTimer((t) => ({
      phase: t.phase,
      running: true,
      endsAt: Date.now() + t.remaining * 1000,
    }))
  }

  const pause = () =>
    setTimer((t) => ({
      phase: t.phase,
      running: false,
      remaining: Math.max(0, (t.endsAt - Date.now()) / 1000),
    }))

  const reset = () =>
    setTimer((t) => ({ phase: t.phase, running: false, remaining: phaseLength(t.phase) }))

  const saveGoals = useCallback(
    async (goals) => {
      const optimistic = {
        ...(state ?? {}),
        goals: goals.map((g, i) => ({ id: g.id ?? `tmp-${i}`, ...g })),
      }
      setLocal(optimistic)
      setSaveError(null)
      try {
        const body = await postJson('/api/goals', { goals })
        if (body?.available) setLocal(body)
        else {
          setSaveError(body?.error ?? 'could not save')
          reload()
        }
      } catch (err) {
        setSaveError(err.message || 'could not save')
        reload()
      }
    },
    [reload, state],
  )

  const progress = useMemo(() => {
    const length = phaseLength(timer.phase)
    return length ? 1 - Math.max(0, Math.min(1, remaining / length)) : 0
  }, [remaining, timer.phase])

  let body
  if (loading && !data) {
    body = <StateBlock kind="loading" title="Loading goals…" />
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
        detail={data?.error ?? 'Goals could not be loaded.'}
        hint={data?.hint ?? 'Check that backend/data/ is writable.'}
      />
    )
  } else {
    body = (
      <div className={`focus ${timer.phase}`}>
        <div className="pomo">
          <div className="pomo-time">{mmss(remaining)}</div>
          <div className="pomo-track">
            <div className="pomo-fill" style={{ width: `${progress * 100}%` }} />
          </div>
          <div className="pomo-meta">
            <span className="pomo-phase">{timer.phase === 'work' ? 'focus' : 'break'}</span>
            <span className="pomo-count" title="Pomodoros completed today">
              {'●'.repeat(Math.min(state.pomodoros, 8))}
              {state.pomodoros > 8 ? '…' : ''}
              <span className="pomo-count-n">{state.pomodoros}</span>
            </span>
          </div>
          <div className="pomo-buttons">
            {timer.running ? (
              <button type="button" onClick={pause}>pause</button>
            ) : (
              <button type="button" className="primary" onClick={start}>start</button>
            )}
            <button type="button" onClick={reset}>reset</button>
          </div>
        </div>
        <Goals state={state} onChange={saveGoals} disabled={false} />
        {saveError ? <div className="focus-error">{saveError}</div> : null}
      </div>
    )
  }

  const done = state ? `${state.done_count}/${state.goals.length}` : '—'
  return (
    <Card
      title="Focus"
      subtitle={state ? `${done} goals · ${state.pomodoros} pomodoro${state.pomodoros === 1 ? '' : 's'}` : '25 / 5'}
      className={`card-focus${flash ? ' flashing' : ''}`}
    >
      {body}
    </Card>
  )
}
