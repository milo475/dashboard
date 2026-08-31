import { useMemo } from 'react'
import { Card, StateBlock } from './Card.jsx'
import { Sparkline } from './Sparkline.jsx'
import { usePolling } from '../api.js'
import { ACCENT_SOFT, DOWN, UP, WARN } from '../theme.js'

const TEMP_COLOR = { normal: UP, warm: WARN, hot: DOWN, unknown: '#6b7688' }

function bytes(value) {
  if (value == null) return '—'
  const units = ['B', 'K', 'M', 'G', 'T']
  let n = value
  let unit = 0
  while (n >= 1024 && unit < units.length - 1) {
    n /= 1024
    unit += 1
  }
  return `${n >= 100 || unit === 0 ? Math.round(n) : n.toFixed(1)}${units[unit]}`
}

const rate = (value) => (value == null ? '—' : `${bytes(value)}/s`)

function duration(seconds) {
  if (!seconds && seconds !== 0) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days) return `${days}d ${hours}h`
  if (hours) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

/* A bar, not a radial gauge: at this size an arc costs pixels and reads no
 * faster, and three stacked bars are directly comparable to each other. */
function Meter({ label, percent, detail, color }) {
  const pct = Math.max(0, Math.min(100, percent ?? 0))
  return (
    <div className="meter">
      <div className="meter-head">
        <span className="meter-label">{label}</span>
        <span className="meter-detail">{detail}</span>
        <span className="meter-pct">{Math.round(pct)}%</span>
      </div>
      <div
        className="meter-track"
        role="meter"
        aria-label={label}
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="meter-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}

export function SystemCard() {
  const { data, error, loading } = usePolling('/api/system', 5_000)

  const history = data?.history ?? []
  const series = useMemo(
    () => ({
      cpu: history.map((point) => point.cpu ?? 0),
      up: history.map((point) => point.up ?? 0),
      down: history.map((point) => point.down ?? 0),
    }),
    [history],
  )

  let body
  if (loading && !data) {
    body = <StateBlock kind="loading" title="Reading vitals…" />
  } else if (error) {
    body = (
      <StateBlock
        kind="error"
        title="No data"
        detail={`Backend unreachable: ${error}`}
        hint="Is dashboard-backend.service running?"
      />
    )
  } else if (!data?.available) {
    body = (
      <StateBlock
        kind="error"
        title="No data"
        detail={data?.error ?? 'Machine vitals are unavailable.'}
        hint={data?.hint ?? 'Install psutil, then restart the backend.'}
      />
    )
  } else {
    const { cpu, memory, disk, network, temperature } = data
    const tempColor = TEMP_COLOR[temperature.level] ?? TEMP_COLOR.unknown
    const cpuColor = cpu.percent >= 85 ? DOWN : cpu.percent >= 60 ? WARN : UP

    body = (
      <div className="sys">
        <div className="sys-row">
          <div className="sys-figure">
            <span className="sys-figure-value" style={{ color: tempColor }}>
              {temperature.celsius == null ? 'n/a' : `${Math.round(temperature.celsius)}°`}
            </span>
            <span className="sys-figure-label">
              cpu temp
              {temperature.celsius == null ? ' · no sensor' : ''}
            </span>
          </div>
          <div className="sys-figure">
            <span className="sys-figure-value">{duration(data.uptime_seconds)}</span>
            <span className="sys-figure-label">uptime</span>
          </div>
          <div className="sys-figure">
            <span className="sys-figure-value">
              {cpu.load ? cpu.load[0].toFixed(2) : '—'}
            </span>
            <span className="sys-figure-label">
              load{cpu.cores ? ` · ${cpu.cores} cores` : ''}
            </span>
          </div>
        </div>

        <div className="meters">
          <Meter
            label="CPU"
            percent={cpu.percent}
            detail={cpu.load ? `${cpu.load.map((l) => l.toFixed(2)).join(' ')}` : ''}
            color={cpuColor}
          />
          <Meter
            label="RAM"
            percent={memory.percent}
            detail={`${bytes(memory.used)} / ${bytes(memory.total)}`}
            color={ACCENT_SOFT}
          />
          <Meter
            label="DISK"
            percent={disk.percent}
            detail={`${bytes(disk.used)} / ${bytes(disk.total)} · ${disk.mount}`}
            color="#0081c6"
          />
        </div>

        <div className="sys-sparks">
          <div className="sys-spark">
            <div className="sys-spark-head">
              <span>cpu</span>
              <span className="sys-spark-value">{cpu.percent.toFixed(0)}%</span>
            </div>
            <Sparkline points={series.cpu} color={cpuColor} width={150} height={30} fill />
          </div>
          <div className="sys-spark">
            <div className="sys-spark-head">
              <span>net ↓</span>
              <span className="sys-spark-value">{rate(network.down)}</span>
            </div>
            <Sparkline points={series.down} color={UP} width={150} height={30} fill />
          </div>
          <div className="sys-spark">
            <div className="sys-spark-head">
              <span>net ↑</span>
              <span className="sys-spark-value">{rate(network.up)}</span>
            </div>
            <Sparkline points={series.up} color={ACCENT_SOFT} width={150} height={30} fill />
          </div>
        </div>
      </div>
    )
  }

  const minutes = data?.history_window ? Math.round(data.history_window / 60) : 10
  return (
    <Card
      title="System"
      subtitle={
        data?.available
          ? `${minutes}m trend · 5s${data.stale ? ' · cached' : ''}`
          : 'psutil · lm-sensors'
      }
      className="card-system"
    >
      {body}
    </Card>
  )
}
