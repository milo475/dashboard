/* Inline sparkline. Deliberately not a recharts chart: these are 20-70px tall,
 * render several to a card, and need no axes, tooltip or layout pass. */
export function Sparkline({
  points,
  color,
  width = 68,
  height = 22,
  fill = false,
  strokeWidth = 2,
}) {
  if (!points || points.length < 2) {
    return <span className="spark-empty" aria-hidden="true">—</span>
  }
  const pad = 2
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const step = (width - pad * 2) / (points.length - 1)
  const xy = points.map((value, index) => [
    pad + index * step,
    height - pad - ((value - min) / span) * (height - pad * 2),
  ])
  const d = xy
    .map(([x, y], index) => `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(' ')
  const area = `${d} L${xy[xy.length - 1][0].toFixed(1)},${height} L${xy[0][0].toFixed(1)},${height} Z`

  return (
    <svg
      className="spark"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="presentation"
    >
      {fill ? <path d={area} fill={color} opacity="0.16" /> : null}
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
