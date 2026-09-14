/* Relative time is computed in the browser, not on the backend, so "2h ago"
 * keeps counting between refreshes instead of freezing. `iso` may also be a
 * unix timestamp in seconds. */
export function timeAgo(when, now) {
  if (when == null) return '—'
  const then = typeof when === 'number' ? when * 1000 : new Date(when).getTime()
  const seconds = (now - then) / 1000
  if (Number.isNaN(seconds)) return '—'
  if (seconds < 60) return 'now'
  const minutes = seconds / 60
  if (minutes < 60) return `${Math.floor(minutes)}m ago`
  const hours = minutes / 60
  if (hours < 24) return `${Math.floor(hours)}h ago`
  const days = hours / 24
  if (days < 30) return `${Math.floor(days)}d ago`
  const months = days / 30
  if (months < 12) return `${Math.floor(months)}mo ago`
  return `${Math.floor(months / 12)}y ago`
}
