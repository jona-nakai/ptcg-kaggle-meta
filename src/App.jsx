import { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const numberFormatter = new Intl.NumberFormat('en-US')

function formatNumber(value) {
  return numberFormatter.format(value ?? 0)
}

function formatBytes(value) {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

function App() {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadSummary() {
      try {
        const response = await fetch('/api/meta')
        if (!response.ok) {
          throw new Error(`API returned ${response.status}`)
        }
        setSummary(await response.json())
      } catch (error) {
        setError(error.message)
      }
    }

    loadSummary()
  }, [])

  const maxCardCount = useMemo(() => {
    return Math.max(...(summary?.topCards ?? []).map((card) => card.count), 1)
  }, [summary])

  if (error) {
    return (
      <main className="page">
        <section className="empty-state">
          <h1>Pokemon TCG Meta</h1>
          <p>Could not load meta data: {error}</p>
        </section>
      </main>
    )
  }

  if (!summary) {
    return (
      <main className="page">
        <section className="empty-state">
          <h1>Pokemon TCG Meta</h1>
          <p>Loading latest deck statistics...</p>
        </section>
      </main>
    )
  }

  return (
    <main className="page">
      <header className="app-header">
        <div>
          <p className="eyebrow">Kaggle Pokemon TCG AI Battle Episodes</p>
          <h1>Pokemon TCG Meta</h1>
        </div>
        <div className="source-badge">
          <span>{summary.source.date}</span>
          <strong>{summary.source.datasetSlug}</strong>
        </div>
      </header>

      <section className="metric-grid" aria-label="Dataset summary">
        <article className="metric">
          <span>Battle files</span>
          <strong>{formatNumber(summary.totals.battleFiles)}</strong>
        </article>
        <article className="metric">
          <span>Parsed decks</span>
          <strong>{formatNumber(summary.totals.parsedDecks)}</strong>
        </article>
        <article className="metric">
          <span>Card copies</span>
          <strong>{formatNumber(summary.totals.cardCopies)}</strong>
        </article>
        <article className="metric">
          <span>Raw daily size</span>
          <strong>{formatBytes(summary.source.reportedTotalBytes)}</strong>
        </article>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Deck inclusion</p>
            <h2>Most Played Cards</h2>
          </div>
          <p>
            Counted from the two full decklists embedded in each parsed battle.
          </p>
        </div>

        <div className="card-list">
          {summary.topCards.map((card, index) => (
            <article className="card-row" key={card.id}>
              <div className="rank">{index + 1}</div>
              <div className="card-copy">
                <strong>{card.name}</strong>
                <span>Card ID {card.id}</span>
              </div>
              <div className="bar-cell">
                <div
                  className="bar"
                  style={{ width: `${(card.count / maxCardCount) * 100}%` }}
                />
              </div>
              <div className="count">{formatNumber(card.count)}</div>
            </article>
          ))}
        </div>
      </section>

      <section className="detail-strip">
        <span>Top avg score: {summary.source.topAvgScore.toFixed(3)}</span>
        <span>Median avg score: {summary.source.medianAvgScore.toFixed(3)}</span>
        <span>Generated: {new Date(summary.generatedAt).toLocaleString()}</span>
      </section>
    </main>
  )
}

createRoot(document.getElementById('root')).render(<App />)
