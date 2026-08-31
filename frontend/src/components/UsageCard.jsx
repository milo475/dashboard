import { useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, StateBlock } from './Card.jsx'
import { colorForApp, SURFACE } from '../theme.js'
import { usePolling } from '../api.js'

const GRID = '#1b2430'
const AXIS_TEXT = '#7d8b9e'

function fmtHours(hours) {
  if (!hours) return '0m'
  const total = Math.round(hours * 60)
  if (total === 0) return '<1m'
  const h = Math.floor(total / 60)
  const m = total % 60
  if (h === 0) return `${m}m`
  return m === 0 ? `${h}h` : `${h}h ${m}m`
}

function UsageTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const rows = payload.filter((r) => r.value > 0).slice().reverse()
  if (!rows.length) return null
  return (
    <div className="tooltip">
      <div className="tooltip-head">{label}</div>
      {rows.map((row) => (
        <div className="tooltip-row" key={row.dataKey}>
          <span className="swatch" style={{ background: row.color }} />
          <span className="tooltip-name">{row.dataKey}</span>
          <span className="tooltip-value">{fmtHours(row.value)}</span>
        </div>
      ))}
    </div>
  )
}

function TotalTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const row = payload[0]
  return (
    <div className="tooltip">
      <div className="tooltip-row">
        <span className="swatch" style={{ background: row.payload.fill }} />
        <span className="tooltip-name">{row.payload.app}</span>
        <span className="tooltip-value">{fmtHours(row.value)}</span>
      </div>
    </div>
  )
}

function Legend({ apps }) {
  return (
    <ul className="legend">
      {apps.map((app) => (
        <li key={app}>
          <span className="swatch" style={{ background: colorForApp(app) }} />
          {app}
        </li>
      ))}
    </ul>
  )
}

export function UsageCard() {
  const { data, error, loading } = usePolling('/api/usage', 60_000)
  const [view, setView] = useState('chart')

  const totals = useMemo(
    () =>
      (data?.totals ?? []).map((row) => ({
        ...row,
        fill: colorForApp(row.app),
      })),
    [data],
  )
  const apps = data?.top_apps ?? []
  const daily = data?.daily ?? []

  /* Below an hour the axis would read "0.075h"; switch the whole axis to
   * minutes so the ticks stay short and never clip. */
  const peak = Math.max(0, ...daily.map((d) => d.total ?? 0))
  const axisTick = useMemo(() => {
    if (peak >= 1) return (v) => `${Math.round(v * 10) / 10}h`
    return (v) => (v ? `${Math.round(v * 60)}m` : '0')
  }, [peak])

  let body
  if (loading && !data) {
    body = <StateBlock kind="loading" title="Loading usage…" />
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
        detail={data?.error ?? 'ActivityWatch is not reachable.'}
        hint={data?.hint ?? 'Start ActivityWatch, then this card fills in.'}
      />
    )
  } else if (!totals.length) {
    body = (
      <StateBlock
        kind="empty"
        title="No activity recorded yet"
        detail="ActivityWatch is connected but has not logged any window time in the last 7 days."
        hint="Keep using the machine — the first events appear within a minute."
      />
    )
  } else if (view === 'table') {
    body = (
      <div className="table-wrap">
        <table className="data-table">
          <caption className="visually-hidden">
            Active time per application over the last 7 days
          </caption>
          <thead>
            <tr>
              <th scope="col">Application</th>
              <th scope="col">7-day total</th>
              <th scope="col">Today</th>
            </tr>
          </thead>
          <tbody>
            {totals.map((row) => {
              const today = (data.today ?? []).find((t) => t.app === row.app)
              return (
                <tr key={row.app}>
                  <th scope="row">
                    <span className="swatch" style={{ background: row.fill }} />
                    {row.app}
                  </th>
                  <td>{fmtHours(row.hours)}</td>
                  <td>{fmtHours(today?.hours ?? 0)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  } else {
    body = (
      <div className="usage-charts">
        <div className="chart-block">
          <h3 className="chart-title">Total active time by app · 7 days</h3>
          <div className="chart-area">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={totals}
              layout="vertical"
              margin={{ top: 4, right: 56, bottom: 4, left: 4 }}
              barCategoryGap={6}
            >
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="app"
                width={104}
                tickLine={false}
                axisLine={false}
                tick={{ fill: AXIS_TEXT, fontSize: 12 }}
                tickFormatter={(name) =>
                  name.length > 13 ? `${name.slice(0, 12)}…` : name
                }
              />
              <Tooltip
                content={<TotalTooltip />}
                cursor={{ fill: 'rgba(0,255,204,0.05)' }}
              />
              <Bar
                dataKey="hours"
                radius={[0, 4, 4, 0]}
                maxBarSize={22}
                isAnimationActive={false}
              >
                {totals.map((row) => (
                  <Cell key={row.app} fill={row.fill} />
                ))}
                <LabelList
                  dataKey="hours"
                  position="right"
                  formatter={fmtHours}
                  fill={AXIS_TEXT}
                  fontSize={11}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-block">
          <h3 className="chart-title">Daily breakdown · last 7 days</h3>
          <div className="chart-area">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={daily}
              margin={{ top: 8, right: 8, bottom: 4, left: 0 }}
              barCategoryGap="22%"
            >
              {/* solid hairline grid, one shade off the surface */}
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={{ stroke: GRID }}
                tick={{ fill: AXIS_TEXT, fontSize: 12 }}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={44}
                tick={{ fill: AXIS_TEXT, fontSize: 11 }}
                tickFormatter={axisTick}
              />
              <Tooltip
                content={<UsageTooltip />}
                cursor={{ fill: 'rgba(0,255,204,0.05)' }}
              />
              {apps.map((app, index) => (
                <Bar
                  key={app}
                  dataKey={app}
                  stackId="day"
                  fill={colorForApp(app)}
                  /* surface-colored stroke = a 2px gap between segments */
                  stroke={SURFACE}
                  strokeWidth={2}
                  maxBarSize={46}
                  isAnimationActive={false}
                  radius={index === apps.length - 1 ? [4, 4, 0, 0] : 0}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
          </div>
        </div>
        <Legend apps={apps} />
      </div>
    )
  }

  const subtitle = data?.available
    ? `${fmtHours(data.today_total_hours)} today · ${fmtHours(data.week_total_hours)} this week${
        data.afk_filtered ? '' : ' · AFK filter off'
      }${data.stale ? ' · cached' : ''}`
    : 'activitywatch'

  return (
    <Card
      title="App usage"
      subtitle={subtitle}
      className="card-usage"
      actions={
        <div className="toggle" role="group" aria-label="Usage view">
          <button
            type="button"
            className={view === 'chart' ? 'on' : ''}
            onClick={() => setView('chart')}
          >
            chart
          </button>
          <button
            type="button"
            className={view === 'table' ? 'on' : ''}
            onClick={() => setView('table')}
          >
            table
          </button>
        </div>
      }
    >
      {body}
    </Card>
  )
}
