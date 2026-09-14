import { useCallback, useEffect, useState } from 'react'
import { Card, StateBlock } from '../Card.jsx'
import { postJson, usePolling } from '../../api.js'

const LISTS = [
  { key: 'work', label: 'Work to-do list' },
  { key: 'personal', label: 'Personal to-do list' },
]

function TodoList({ label, items, max, onChange }) {
  const [draft, setDraft] = useState('')
  const full = items.length >= max

  const submit = (event) => {
    event.preventDefault()
    const text = draft.trim()
    if (!text || full) return
    setDraft('')
    onChange([...items, { id: `tmp-${Date.now()}`, text, done: false }])
  }

  return (
    <section className="todo-list">
      <h3 className="todo-heading">{label}</h3>
      <ul className="todo-items">
        {items.map((item) => (
          <li key={item.id} className={item.done ? 'done' : ''}>
            <button
              type="button"
              className="todo-toggle"
              aria-pressed={item.done}
              onClick={() =>
                onChange(items.map((i) => (i.id === item.id ? { ...i, done: !i.done } : i)))
              }
            >
              <span className="todo-box" aria-hidden="true">{item.done ? '✓' : ''}</span>
              <span className="todo-text">{item.text}</span>
            </button>
            <button
              type="button"
              className="todo-remove"
              aria-label={`Remove ${item.text}`}
              onClick={() => onChange(items.filter((i) => i.id !== item.id))}
            >
              ×
            </button>
          </li>
        ))}
        {items.length === 0 ? <li className="todo-empty">Nothing here yet.</li> : null}
      </ul>
      <form className="todo-add" onSubmit={submit}>
        <input
          type="text"
          value={draft}
          maxLength={120}
          disabled={full}
          placeholder={full ? `Max ${max} items` : 'Add an item…'}
          aria-label={`Add to ${label}`}
          onChange={(event) => setDraft(event.target.value)}
        />
        <button type="submit" disabled={full || !draft.trim()}>
          add
        </button>
      </form>
    </section>
  )
}

export function TodoCard() {
  const { data, error, loading, reload } = usePolling('/api/todos', 60_000)
  const [local, setLocal] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const state = local ?? (data?.available ? data : null)

  useEffect(() => {
    if (data?.available) setLocal(null)
  }, [data])

  const save = useCallback(
    async (key, items) => {
      const lists = { ...state.lists, [key]: items }
      setLocal({ ...state, lists })
      setSaveError(null)
      try {
        const body = await postJson('/api/todos', { lists })
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

  let body
  if (loading && !data) {
    body = <StateBlock kind="loading" title="Loading lists…" />
  } else if (error && !state) {
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
        detail={data?.error ?? 'The to-do lists could not be loaded.'}
        hint={data?.hint ?? 'Check that backend/data/ is writable.'}
      />
    )
  } else {
    body = (
      <div className="todo-note">
        {LISTS.map((list) => (
          <TodoList
            key={list.key}
            label={list.label}
            items={state.lists[list.key] ?? []}
            max={state.max_items ?? 12}
            onChange={(items) => save(list.key, items)}
          />
        ))}
        {saveError ? <div className="todo-error">{saveError}</div> : null}
      </div>
    )
  }

  const all = state ? LISTS.flatMap((l) => state.lists[l.key] ?? []) : []
  const done = all.filter((i) => i.done).length
  return (
    <Card
      title="To-do list"
      subtitle={state ? `${done}/${all.length} done` : 'work · personal'}
      className="card-todo"
    >
      {body}
    </Card>
  )
}
