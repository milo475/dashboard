import { Card, StateBlock } from './Card.jsx'
import { usePolling } from '../api.js'

export function NewsCard() {
  const { data, error, loading } = usePolling('/api/ai-news', 3_600_000)

  let body
  if (loading && !data) {
    body = <StateBlock kind="loading" title="Loading feed…" />
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
        detail={data?.error ?? 'The news sources could not be reached.'}
        hint={data?.hint ?? 'Check the internet connection.'}
      />
    )
  } else if (!data.items?.length) {
    body = <StateBlock kind="empty" title="Nothing matched the AI filter this hour." />
  } else {
    body = (
      <ol className="news-list">
        {data.items.map((item) => (
          <li key={item.url}>
            <a href={item.url} target="_blank" rel="noreferrer noopener">
              <span className={`tag ${item.source === 'Hacker News' ? 'tag-hn' : 'tag-arxiv'}`}>
                {item.source === 'Hacker News' ? 'HN' : 'arXiv'}
              </span>
              <span className="news-title">{item.title}</span>
              {typeof item.score === 'number' ? (
                <span className="news-score">{item.score}</span>
              ) : null}
            </a>
          </li>
        ))}
      </ol>
    )
  }

  return (
    <Card
      title="AI feed"
      subtitle={data?.stale ? 'cached · retrying' : 'hacker news + arxiv · hourly'}
      className="card-news"
    >
      {body}
    </Card>
  )
}
