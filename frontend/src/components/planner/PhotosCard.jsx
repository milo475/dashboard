import { useCallback, useEffect, useRef, useState } from 'react'
import { Card, StateBlock } from '../Card.jsx'

const SLOTS = 3
const ROTATE_MS = 20_000
const IMAGE_NAME = /\.(jpe?g|png|webp|gif|avif)$/i

async function send(path, options) {
  const res = await fetch(path, { headers: { Accept: 'application/json' }, ...options })
  const body = await res.json().catch(() => ({}))
  if (!res.ok || body.available === false) throw new Error(body.error ?? `HTTP ${res.status}`)
  return body
}

/* Three tall tiles, like the collage on the reference desktop. Photos come
 * from backend/data/photos: pick them with the button, drop them on the card,
 * or copy files into the folder. With more than three the strip slides one
 * photo along every 20s. */
export function PhotosCard({ photos, dir, loading, error, reload }) {
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState(null)
  const [dragging, setDragging] = useState(false)
  const input = useRef(null)
  const count = photos?.length ?? 0

  useEffect(() => {
    if (count <= SLOTS) return undefined
    const id = setInterval(() => setOffset((value) => value + 1), ROTATE_MS)
    return () => clearInterval(id)
  }, [count])

  useEffect(() => {
    if (!status || status.kind === 'pending') return undefined
    const id = setTimeout(() => setStatus(null), 6000)
    return () => clearTimeout(id)
  }, [status])

  const upload = useCallback(
    async (fileList) => {
      const files = Array.from(fileList ?? []).filter(
        (file) => file.type.startsWith('image/') || IMAGE_NAME.test(file.name),
      )
      if (!files.length) {
        setStatus({ kind: 'error', message: 'no images in that selection' })
        return
      }
      const form = new FormData()
      files.forEach((file) => form.append('photos', file, file.name))
      setStatus({ kind: 'pending', message: `uploading ${files.length}…` })
      try {
        const body = await send('/api/photos', { method: 'POST', body: form })
        const skipped = body.rejected?.length ? ` · ${body.rejected.length} skipped` : ''
        setStatus({ kind: 'ok', message: `added ${body.saved?.length ?? 0}${skipped}` })
        reload?.()
      } catch (err) {
        setStatus({ kind: 'error', message: err.message || 'upload failed' })
      }
    },
    [reload],
  )

  const remove = useCallback(
    async (photo) => {
      if (!window.confirm(`Remove ${photo.name} from the dashboard?`)) return
      setStatus({ kind: 'pending', message: 'removing…' })
      try {
        await send(`/api/photos/${encodeURIComponent(photo.name)}`, { method: 'DELETE' })
        setStatus({ kind: 'ok', message: `removed ${photo.name}` })
        reload?.()
      } catch (err) {
        setStatus({ kind: 'error', message: err.message || 'could not remove' })
      }
    },
    [reload],
  )

  const onDragOver = (event) => {
    event.preventDefault()
    if (!dragging) setDragging(true)
  }
  const onDragLeave = () => setDragging(false)
  const onDrop = (event) => {
    event.preventDefault()
    setDragging(false)
    upload(event.dataTransfer?.files)
  }

  const pick = () => input.current?.click()

  let body
  if (loading) {
    body = <StateBlock kind="loading" title="Looking for photos…" />
  } else if (error) {
    body = (
      <StateBlock
        kind="error"
        title="No data"
        detail={`Backend unreachable: ${error}`}
        hint="Is dashboard-backend.service running?"
      />
    )
  } else if (count === 0) {
    body = (
      <div className="collage collage-empty">
        {Array.from({ length: SLOTS }, (_, index) => (
          <button
            key={index}
            type="button"
            className="collage-item placeholder"
            aria-label="Add photos"
            onClick={pick}
          >
            {index === 1 ? <span className="placeholder-plus">+</span> : null}
          </button>
        ))}
        <p className="collage-hint">
          Drop photos here, press <b>+ add photos</b>, or copy files into{' '}
          <code>{dir ?? 'backend/data/photos'}</code>
        </p>
      </div>
    )
  } else {
    const shown = Array.from({ length: Math.min(SLOTS, count) }, (_, index) => photos[(offset + index) % count])
    body = (
      <div className="collage">
        {shown.map((photo) => (
          <figure key={photo.name} className="collage-item">
            <img src={photo.url} alt="" loading="lazy" />
            <button
              type="button"
              className="collage-remove"
              aria-label={`Remove ${photo.name}`}
              title="Remove"
              onClick={() => remove(photo)}
            >
              ×
            </button>
          </figure>
        ))}
      </div>
    )
  }

  return (
    <Card
      title="Photos"
      subtitle={count ? `${count} photo${count === 1 ? '' : 's'}${count > SLOTS ? ' · rotating' : ''}` : 'drop or add'}
      className="card-photos"
      actions={
        <>
          <input
            ref={input}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(event) => {
              upload(event.target.files)
              event.target.value = ''
            }}
          />
          <button type="button" className="photos-add" onClick={pick}>
            + add photos
          </button>
        </>
      }
    >
      <div
        className={`photos${dragging ? ' dragging' : ''}`}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        {body}
        <div className={`photos-status ${status ? status.kind : ''}`} role="status">
          {status ? status.message : ''}
        </div>
      </div>
    </Card>
  )
}
