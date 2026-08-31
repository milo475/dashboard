import { useEffect, useState } from 'react'

export function Clock() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  const ss = String(now.getSeconds()).padStart(2, '0')
  const date = now.toLocaleDateString(undefined, {
    weekday: 'long',
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  })

  return (
    <div className="clock">
      <div className="clock-time">
        <span>{hh}</span>
        <span className="clock-colon">:</span>
        <span>{mm}</span>
        <span className="clock-seconds">{ss}</span>
      </div>
      <div className="clock-date">{date}</div>
    </div>
  )
}
