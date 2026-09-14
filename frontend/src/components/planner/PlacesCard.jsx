import { useCallback, useEffect, useState } from 'react'
import { Card, StateBlock } from '../Card.jsx'
import { usePolling } from '../../api.js'
import { timeAgo } from '../../time.js'

function FolderIcon() {
  return (
    <svg viewBox="0 0 48 40" aria-hidden="true" focusable="false">
      <path
        d="M4 9a4 4 0 0 1 4-4h11.2a4 4 0 0 1 2.8 1.2L24.6 9H40a4 4 0 0 1 4 4v18a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z"
        fill="currentColor"
      />
      <path d="M4 15h40v16a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z" fill="currentColor" opacity="0.72" />
    </svg>
  )
}

function FileIcon({ kind }) {
  return (
    <svg viewBox="0 0 32 40" aria-hidden="true" focusable="false">
      <path d="M4 2h16l8 8v28H4z" fill="currentColor" />
      <path d="M20 2v8h8z" fill="#fff" opacity="0.45" />
      {kind ? (
        <text x="16" y="31" textAnchor="middle" fontSize="8" fontWeight="700" fill="#fff" opacity="0.9">
          {kind.slice(0, 4).toUpperCase()}
        </text>
      ) : null}
    </svg>
  )
}

/* Folder shortcuts and the newest files, each opening on the desktop through
 * the backend (it only opens paths it listed itself). */
export function PlacesCard() {
  const folders = usePolling('/api/folders', 300_000)
  const files = usePolling('/api/files', 30_000)
  const [status, setStatus] = useState(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    if (!status || status.kind === 'pending') return undefined
    const id = setTimeout(() => setStatus(null), 5000)
    return () => clearTimeout(id)
  }, [status])

  const open = useCallback(async (target, label) => {
    setStatus({ kind: 'pending', message: `opening ${label}…` })
    try {
      const res = await fetch('/api/open', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(target),
      })
      const body = await res.json().catch(() => ({}))
      setStatus(
        res.ok && body.ok
          ? { kind: 'ok', message: `opened ${body.opened ?? label}` }
          : { kind: 'error', message: body.error ?? `failed (HTTP ${res.status})` },
      )
    } catch (err) {
      setStatus({ kind: 'error', message: err.message || 'request failed' })
    }
  }, [])

  const folderRows = folders.data?.available ? folders.data.folders : []
  const fileRows = files.data?.available ? files.data.files : []

  let body
  if (folders.error && files.error) {
    body = (
      <StateBlock
        kind="error"
        title="No data"
        detail={`Backend unreachable: ${folders.error}`}
        hint="Is dashboard-backend.service running?"
      />
    )
  } else {
    body = (
      <div className="places">
        <section className="places-col">
          <h3 className="places-heading">Folders</h3>
          <div className="folder-grid">
            {folderRows.map((folder) => (
              <button
                key={folder.id}
                type="button"
                className="folder"
                disabled={!folder.exists}
                title={folder.exists ? folder.path : `${folder.path} (missing)`}
                onClick={() => open({ folder: folder.id }, folder.name)}
              >
                <FolderIcon />
                <span className="folder-name">{folder.name}</span>
              </button>
            ))}
            {folders.data && folderRows.length === 0 ? (
              <p className="places-empty">Add shortcuts in backend/data/folders.json.</p>
            ) : null}
          </div>
        </section>
        <section className="places-col">
          <h3 className="places-heading">Files</h3>
          <ul className="file-list">
            {fileRows.map((file) => (
              <li key={file.path}>
                <button
                  type="button"
                  className="file"
                  title={file.path}
                  onClick={() => open({ file: file.path }, file.name)}
                >
                  <FileIcon kind={file.kind} />
                  <span className="file-name">{file.name}</span>
                  <span className="file-meta">
                    {file.dir} · {timeAgo(file.modified, now)}
                  </span>
                </button>
              </li>
            ))}
            {files.data && fileRows.length === 0 ? (
              <li className="places-empty">No recent files.</li>
            ) : null}
          </ul>
        </section>
        <div className={`places-status ${status ? status.kind : ''}`} role="status">
          {status ? status.message : ''}
        </div>
      </div>
    )
  }

  return (
    <Card
      title="Folders · Files"
      subtitle={files.data?.available ? files.data.dirs.join(' · ') : 'click to open'}
      className="card-places"
    >
      {body}
    </Card>
  )
}
