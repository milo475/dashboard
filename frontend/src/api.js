import { useCallback, useEffect, useRef, useState } from 'react'

/* Polls a JSON endpoint on an interval.
 *
 * The backend always answers 200 with an {available} envelope, so a reachable
 * backend reporting a dead upstream lands in `data` (available:false) rather
 * than in `error`. `error` means the backend itself could not be reached. */
export function usePolling(path, intervalMs) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [updatedAt, setUpdatedAt] = useState(null)
  const alive = useRef(true)

  const load = useCallback(async () => {
    try {
      const res = await fetch(path, { headers: { Accept: 'application/json' } })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const body = await res.json()
      if (!alive.current) return
      setData(body)
      setError(null)
      setUpdatedAt(Date.now())
    } catch (err) {
      if (!alive.current) return
      setError(err.message || 'request failed')
    } finally {
      if (alive.current) setLoading(false)
    }
  }, [path])

  useEffect(() => {
    alive.current = true
    load()
    const id = setInterval(load, intervalMs)
    return () => {
      alive.current = false
      clearInterval(id)
    }
  }, [load, intervalMs])

  return { data, error, loading, updatedAt, reload: load }
}

/* POST JSON and return the parsed body.
 *
 * Mirrors the GET contract: the backend answers 200 with {available:false} for
 * a refused write, so callers check `available` rather than catching. A thrown
 * error here means the backend itself could not be reached. */
export async function postJson(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
