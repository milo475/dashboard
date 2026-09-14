import { UsageCard } from '../components/UsageCard.jsx'
import { StocksCard } from '../components/StocksCard.jsx'
import { NewsCard } from '../components/NewsCard.jsx'
import { SystemCard } from '../components/SystemCard.jsx'
import { FocusCard } from '../components/FocusCard.jsx'
import { GithubCard } from '../components/GithubCard.jsx'
import { ProductivityCard } from '../components/ProductivityCard.jsx'

/* The monitoring board: three columns at 1920x1080, placed by named area
 * rather than by DOM order - charts left, the two glanceable cards down the
 * middle, the feeds that scroll on the right. */
export function Board() {
  return (
    <main className="grid grid-board">
      <UsageCard />
      <ProductivityCard />
      <SystemCard />
      <FocusCard />
      <StocksCard />
      <GithubCard />
      <NewsCard />
    </main>
  )
}
