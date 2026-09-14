import { Card, StateBlock } from './Card.jsx'
/* Sparkline over the prices the backend has observed since it started.
 * The Finnhub free tier has no candle endpoint, so the series builds up live. */
import { Sparkline } from './Sparkline.jsx'
import { usePolling } from '../api.js'
import { usePalette } from '../ThemeContext.jsx'

const money = (value) =>
  typeof value === 'number'
    ? value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : '—'

export function StocksCard() {
  const { data, error, loading } = usePolling('/api/stocks', 60_000)
  const { up: UP, down: DOWN } = usePalette()

  let body
  if (loading && !data) {
    body = <StateBlock kind="loading" title="Loading quotes…" />
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
        detail={data?.error ?? 'Quotes are unavailable.'}
        hint={data?.hint ?? 'Check the internet connection.'}
      />
    )
  } else {
    body = (
      <div className="table-wrap">
        <table className="data-table stocks-table">
          <caption className="visually-hidden">Top 10 companies by market value</caption>
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col" className="num">Price</th>
              <th scope="col" className="num">Change</th>
              <th scope="col" className="num">Trend</th>
            </tr>
          </thead>
          <tbody>
            {data.stocks.map((row) => {
              const up = (row.change_pct ?? 0) >= 0
              const color = up ? UP : DOWN
              return (
                <tr key={row.symbol}>
                  <th scope="row">
                    <span className="ticker">{row.symbol}</span>
                    <span className="company">{row.name}</span>
                  </th>
                  {row.ok ? (
                    <>
                      <td className="num price">{money(row.price)}</td>
                      <td className="num" style={{ color }}>
                        {up ? '▲' : '▼'} {Math.abs(row.change_pct ?? 0).toFixed(2)}%
                      </td>
                      <td className="num">
                        <Sparkline points={row.sparkline} color={color} />
                      </td>
                    </>
                  ) : (
                    <td className="num muted" colSpan={3}>
                      no quote
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <Card
      title="Markets"
      subtitle={data?.stale ? 'cached · retrying' : 'finnhub · 60s'}
      className="card-stocks"
    >
      {body}
    </Card>
  )
}
