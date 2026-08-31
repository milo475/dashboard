export function Card({ title, subtitle, actions, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      <header className="card-head">
        <div className="card-titles">
          <h2>{title}</h2>
          {subtitle ? <span className="card-sub">{subtitle}</span> : null}
        </div>
        {actions ? <div className="card-actions">{actions}</div> : null}
      </header>
      <div className="card-body">{children}</div>
    </section>
  )
}

/* Shared empty/error/loading state so a dead upstream degrades to a readable
 * card instead of a blank panel or a crash. */
export function StateBlock({ kind = 'empty', title, detail, hint }) {
  return (
    <div className={`state state-${kind}`}>
      <div className="state-title">{title}</div>
      {detail ? <div className="state-detail">{detail}</div> : null}
      {hint ? <div className="state-hint">{hint}</div> : null}
    </div>
  )
}
