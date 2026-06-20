import { useCallback, useEffect, useRef, useState } from 'react'
import { Analytics } from '@vercel/analytics/react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const numberFormatter = new Intl.NumberFormat('en-US')
const competitionUrl =
  'https://www.kaggle.com/competitions/pokemon-tcg-ai-battle'
const episodesIndexUrl =
  'https://www.kaggle.com/datasets/kaggle/pokemon-tcg-ai-battle-episodes-index'

function formatNumber(value) {
  return numberFormatter.format(value ?? 0)
}

function formatPercent(value) {
  return `${(Number(value) * 100).toFixed(1)}%`
}

function pathDate() {
  const value = window.location.pathname.replace(/^\/+/, '').split('/')[0]
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : ''
}

function currentRoute() {
  const parts = window.location.pathname.replace(/^\/+/, '').split('/')
  if (parts[0] === 'archetype' && parts[1]) {
    return {
      page: 'archetype',
      slug: decodeURIComponent(parts[1]),
      date: new URLSearchParams(window.location.search).get('date') || '',
    }
  }
  return { page: 'dashboard', date: pathDate() }
}

function normalizeSearch(value) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
}

function barWidth(value, maxValue) {
  const count = Number(value)
  const max = Number(maxValue)
  if (!Number.isFinite(count) || !Number.isFinite(max) || max <= 0) {
    return '0%'
  }
  return `${Math.min((count / max) * 100, 100)}%`
}

function matchupBarStyle(winRate) {
  const value = Number(winRate)
  if (!Number.isFinite(value)) {
    return {
      width: '0%',
      '--matchup-color-start': '#d97706',
      '--matchup-color-end': '#fbbf24',
    }
  }

  const clamped = Math.max(0, Math.min(value, 1))
  const hue = Math.round(clamped * 120)
  const start = `hsl(${hue} 72% 38%)`
  const end = `hsl(${hue} 78% 54%)`

  return {
    width: barWidth(clamped, 1),
    '--matchup-color-start': start,
    '--matchup-color-end': end,
  }
}

function winRateBadgeStyle(winRate) {
  const value = Number(winRate)
  const clamped = Number.isFinite(value) ? Math.max(0, Math.min(value, 1)) : 0.5
  const hue = Math.round(clamped * 120)
  return {
    '--win-rate-bg': `hsl(${hue} 62% 18%)`,
    '--win-rate-border': `hsl(${hue} 64% 34%)`,
    '--win-rate-text': `hsl(${hue} 86% 78%)`,
  }
}

function Header({ children, dates, selectedDate, onDateChange, showLinks = true, showDatePicker = true }) {
  return (
    <header className="app-header">
      <div>
        {children}
        {showLinks ? (
          <div className="header-links">
            <a className="competition-link" href={competitionUrl} target="_blank" rel="noreferrer">
              Kaggle Competition Link
            </a>
            <span className="header-link-separator">/</span>
            <a className="competition-link" href={episodesIndexUrl} target="_blank" rel="noreferrer">
              Kaggle Competition Data Link
            </a>
          </div>
        ) : null}
      </div>

      {showDatePicker && dates?.length > 0 ? (
        <label className="date-picker">
          <span>Date</span>
          <div className="select-shell">
            <select value={selectedDate} onChange={onDateChange}>
              {dates.map((date) => (
                <option value={date} key={date}>
                  {date}
                </option>
              ))}
            </select>
          </div>
        </label>
      ) : null}
    </header>
  )
}

function CardIdentity({ card, detail }) {
  return (
    <div className="card-identity">
      {card.imageUrl ? (
        <span className="card-preview">
          <img className="card-thumb" src={card.imageUrl} alt="" loading="lazy" tabIndex="0" />
          <span className="card-preview-popover" aria-hidden="true">
            <img src={card.imageUrl} alt="" loading="lazy" />
          </span>
        </span>
      ) : (
        <div className="card-thumb card-thumb-placeholder" aria-hidden="true" />
      )}
      <div className="card-copy">
        <strong>{card.name}</strong>
        <span>{detail ?? `Card ID ${card.id}`}</span>
      </div>
    </div>
  )
}

function App() {
  const [route, setRoute] = useState(currentRoute)
  const [meta, setMeta] = useState(null)
  const [archetypeDetail, setArchetypeDetail] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [archetypeSearch, setArchetypeSearch] = useState('')
  const [countSearch, setCountSearch] = useState('')
  const [inclusionSearch, setInclusionSearch] = useState('')
  const [archetypePage, setArchetypePage] = useState(1)
  const [countPage, setCountPage] = useState(1)
  const [inclusionPage, setInclusionPage] = useState(1)
  const requestIdRef = useRef(0)

  const loadMeta = useCallback(async (date = pathDate(), replaceUrl = false) => {
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    setLoading(true)
    setError('')
    setArchetypeDetail(null)

    try {
      const params = new URLSearchParams()
      if (date) params.set('date', date)
      params.set('page', '1')

      const response = await fetch(`/api/meta?${params.toString()}`)
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`)
      }

      const nextMeta = await response.json()
      if (requestIdRef.current !== requestId) return

      setMeta(nextMeta)
      setArchetypePage(1)
      setCountPage(1)
      setInclusionPage(1)

      const targetPath = `/${nextMeta.date}`
      if (window.location.pathname !== targetPath || replaceUrl || nextMeta.redirected) {
        window.history.replaceState({}, '', targetPath)
      }
    } catch (error) {
      if (requestIdRef.current !== requestId) return
      setError(error.message)
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false)
      }
    }
  }, [])

  const loadArchetype = useCallback(async (slug, date = '') => {
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    setLoading(true)
    setError('')
    setArchetypeDetail(null)

    try {
      const params = new URLSearchParams({ slug })
      if (date) params.set('date', date)

      const response = await fetch(`/api/archetype?${params.toString()}`)
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`)
      }

      const detail = await response.json()
      if (requestIdRef.current !== requestId) return

      setArchetypeDetail(detail)

      const targetPath = `/archetype/${encodeURIComponent(detail.archetype.slug)}?date=${detail.date}`
      if (`${window.location.pathname}${window.location.search}` !== targetPath || detail.redirected) {
        window.history.replaceState({}, '', targetPath)
      }
    } catch (error) {
      if (requestIdRef.current !== requestId) return
      setError(error.message)
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    if (route.page === 'archetype') {
      loadArchetype(route.slug, route.date)
    } else {
      loadMeta(route.date, true)
    }
  }, [loadArchetype, loadMeta, route])

  useEffect(() => {
    function handlePopState() {
      setRoute(currentRoute())
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  function navigate(path) {
    window.history.pushState({}, '', path)
    setRoute(currentRoute())
  }

  async function selectDashboardDate(event) {
    await loadMeta(event.target.value, true)
  }

  async function selectArchetypeDate(event) {
    if (!archetypeDetail) return
    await loadArchetype(archetypeDetail.archetype.slug, event.target.value)
  }

  if (error) {
    return (
      <main className="page">
        <section className="empty-state">
          <h1>Kaggle PTCG Meta</h1>
          <p>Could not load meta data: {error}</p>
        </section>
      </main>
    )
  }

  if (loading && route.page === 'archetype' && !archetypeDetail) {
    return (
      <main className="page">
        <section className="empty-state">
          <h1>Kaggle PTCG Meta</h1>
          <p>Loading archetype...</p>
        </section>
      </main>
    )
  }

  if (route.page === 'archetype' && archetypeDetail) {
    return (
      <ArchetypePage
        detail={archetypeDetail}
        loading={loading}
        onDateChange={selectArchetypeDate}
        onBack={() => navigate(`/${archetypeDetail.date}`)}
        onMatchupClick={(slug) => navigate(`/archetype/${encodeURIComponent(slug)}?date=${archetypeDetail.date}`)}
      />
    )
  }

  if (!meta) {
    return (
      <main className="page">
        <section className="empty-state">
          <h1>Kaggle PTCG Meta</h1>
          <p>Loading latest deck statistics...</p>
        </section>
      </main>
    )
  }

  return (
    <Dashboard
      meta={meta}
      loading={loading}
      archetypeSearch={archetypeSearch}
      countSearch={countSearch}
      inclusionSearch={inclusionSearch}
      archetypePage={archetypePage}
      countPage={countPage}
      inclusionPage={inclusionPage}
      setArchetypeSearch={setArchetypeSearch}
      setCountSearch={setCountSearch}
      setInclusionSearch={setInclusionSearch}
      setArchetypePage={setArchetypePage}
      setCountPage={setCountPage}
      setInclusionPage={setInclusionPage}
      onDateChange={selectDashboardDate}
      onArchetypeClick={(archetype) =>
        navigate(`/archetype/${encodeURIComponent(archetype.slug)}?date=${meta.date}`)
      }
    />
  )
}

function Dashboard({
  meta,
  loading,
  archetypeSearch,
  countSearch,
  inclusionSearch,
  archetypePage,
  countPage,
  inclusionPage,
  setArchetypeSearch,
  setCountSearch,
  setInclusionSearch,
  setArchetypePage,
  setCountPage,
  setInclusionPage,
  onDateChange,
  onArchetypeClick,
}) {
  const cards = meta.cardUsage ?? []
  const normalizedArchetypeSearch = normalizeSearch(archetypeSearch.trim())
  const normalizedCountSearch = normalizeSearch(countSearch.trim())
  const normalizedInclusionSearch = normalizeSearch(inclusionSearch.trim())
  const filteredCountCards = cards
    .filter((card) => normalizeSearch(card.name).includes(normalizedCountSearch))
    .sort((a, b) => b.copiesPlayed - a.copiesPlayed)
  const pageSize = 10
  const countStart = (countPage - 1) * pageSize
  const countRows = filteredCountCards.slice(countStart, countStart + pageSize)
  const hasNextCountPage = countStart + pageSize < filteredCountCards.length
  const maxCopies = Math.max(...cards.map((card) => card.copiesPlayed), 1)
  const totalDecks = Math.max(Number(meta.totalDecks), 1)
  const filteredInclusionCards = cards
    .filter((card) => normalizeSearch(card.name).includes(normalizedInclusionSearch))
    .sort((a, b) => b.decksPlayed - a.decksPlayed)
  const inclusionStart = (inclusionPage - 1) * pageSize
  const inclusionRows = filteredInclusionCards.slice(inclusionStart, inclusionStart + pageSize)
  const hasNextInclusionPage = inclusionStart + pageSize < filteredInclusionCards.length
  const archetypes = (meta.archetypes ?? []).sort((a, b) => b.appearances - a.appearances)
  const filteredArchetypes = archetypes.filter((archetype) => {
    const signatureText = archetype.signatureCards.map((card) => card.name).join(' ')
    return normalizeSearch(`${archetype.name} ${signatureText}`).includes(normalizedArchetypeSearch)
  })
  const archetypeStart = (archetypePage - 1) * pageSize
  const archetypeRows = filteredArchetypes.slice(archetypeStart, archetypeStart + pageSize)
  const hasNextArchetypePage = archetypeStart + pageSize < filteredArchetypes.length
  const maxArchetypeAppearances = Math.max(...archetypes.map((row) => row.appearances), 1)

  return (
    <main className="page">
      <Header dates={meta.availableDates} selectedDate={meta.date} onDateChange={onDateChange}>
        <h1>Kaggle PTCG Meta</h1>
      </Header>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Archetypes</h2>
            <p className="section-subtitle">Share of parsed decklists assigned to each archetype. Sorted by meta share.</p>
          </div>
          <div className="table-controls">
            <input
              className="search-input"
              type="search"
              placeholder="Search archetypes"
              value={archetypeSearch}
              onChange={(event) => {
                setArchetypeSearch(event.target.value)
                setArchetypePage(1)
              }}
            />
            <div className="pager">
              <button type="button" onClick={() => setArchetypePage((page) => Math.max(page - 1, 1))} disabled={archetypePage <= 1 || loading}>
                Previous
              </button>
              <span>Page {archetypePage}</span>
              <button type="button" onClick={() => setArchetypePage((page) => page + 1)} disabled={!hasNextArchetypePage || loading}>
                Next
              </button>
            </div>
          </div>
        </div>

        <div className="card-list" aria-busy={loading}>
          {archetypeRows.map((archetype) => (
            <button
              className="card-row archetype-row"
              type="button"
              key={archetype.id}
              onClick={() => onArchetypeClick(archetype)}
            >
              <div className="card-copy">
                <strong>{archetype.name}</strong>
                <span>{archetype.signatureCards.map((card) => card.name).join(', ')}</span>
                <span className="secondary-metric win-rate-badge" style={winRateBadgeStyle(archetype.winRate)}>
                  Win rate {formatPercent(archetype.winRate)}
                </span>
              </div>
              <div className="bar-cell">
                <div className="bar archetype-bar" style={{ width: barWidth(archetype.appearances, maxArchetypeAppearances) }} />
              </div>
              <div className="count">
                <strong>{formatPercent(archetype.metaShare)}</strong>
                <span>meta share</span>
                <span>{formatNumber(archetype.appearances)} decklists</span>
              </div>
            </button>
          ))}
          {filteredArchetypes.length === 0 ? (
            <p className="empty-table-note">No archetypes have been generated for this date yet.</p>
          ) : null}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Deck Inclusion</h2>
            <p className="section-subtitle">Share of parsed decklists containing at least one copy.</p>
          </div>
          <div className="table-controls">
            <input
              className="search-input"
              type="search"
              placeholder="Search cards"
              value={inclusionSearch}
              onChange={(event) => {
                setInclusionSearch(event.target.value)
                setInclusionPage(1)
              }}
            />
            <div className="pager">
              <button type="button" onClick={() => setInclusionPage((page) => Math.max(page - 1, 1))} disabled={inclusionPage <= 1 || loading}>
                Previous
              </button>
              <span>Page {inclusionPage}</span>
              <button type="button" onClick={() => setInclusionPage((page) => page + 1)} disabled={!hasNextInclusionPage || loading}>
                Next
              </button>
            </div>
          </div>
        </div>

        <div className="card-list" aria-busy={loading}>
          {inclusionRows.map((card) => {
            const percentage = card.decksPlayed / totalDecks
            return (
              <article className="card-row inclusion-row" key={card.id}>
                <CardIdentity card={card} />
                <div className="bar-cell">
                  <div className="bar inclusion-bar" style={{ width: barWidth(card.decksPlayed, totalDecks) }} />
                </div>
                <div className="count">
                  <strong>{formatPercent(percentage)}</strong>
                  <span>{formatNumber(card.decksPlayed)} decks</span>
                </div>
              </article>
            )
          })}
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Card Count</h2>
            <p className="section-subtitle">Total copies found across parsed decklists.</p>
          </div>
          <div className="table-controls">
            <input
              className="search-input"
              type="search"
              placeholder="Search cards"
              value={countSearch}
              onChange={(event) => {
                setCountSearch(event.target.value)
                setCountPage(1)
              }}
            />
            <div className="pager">
              <button type="button" onClick={() => setCountPage((page) => Math.max(page - 1, 1))} disabled={countPage <= 1 || loading}>
                Previous
              </button>
              <span>Page {countPage}</span>
              <button type="button" onClick={() => setCountPage((page) => page + 1)} disabled={!hasNextCountPage || loading}>
                Next
              </button>
            </div>
          </div>
        </div>

        <div className="card-list" aria-busy={loading}>
          {countRows.map((card) => (
            <article className="card-row" key={card.id}>
              <CardIdentity card={card} />
              <div className="bar-cell">
                <div className="bar" style={{ width: barWidth(card.copiesPlayed, maxCopies) }} />
              </div>
              <div className="count">{formatNumber(card.copiesPlayed)}</div>
            </article>
          ))}
        </div>
      </section>
    </main>
  )
}

function ArchetypePage({ detail, loading, onDateChange, onBack, onMatchupClick }) {
  const maxInclusion = 1
  const [activeSection, setActiveSection] = useState('cards')

  return (
    <main className="page">
      <Header
        dates={detail.availableDates}
        selectedDate={detail.date}
        onDateChange={onDateChange}
        showLinks={false}
        showDatePicker={false}
      >
        <button className="back-button" type="button" onClick={onBack}>
          Back to meta
        </button>
        <h1>{detail.archetype.name}</h1>
        <p className="archetype-summary">
          {formatPercent(detail.archetype.metaShare)} meta share · {formatNumber(detail.archetype.appearances)} parsed decklists · {formatPercent(detail.archetype.winRate)} win rate
        </p>
      </Header>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>{activeSection === 'cards' ? 'Cards' : 'Matchups'}</h2>
            <p className="section-subtitle">
              {activeSection === 'cards'
                ? 'How often each card appears inside this archetype.'
                : 'Win rates against other classified archetypes.'}
            </p>
          </div>
          <div className="section-switch" role="tablist" aria-label="Deck detail section">
            <button
              className={activeSection === 'cards' ? 'active' : ''}
              type="button"
              role="tab"
              aria-selected={activeSection === 'cards'}
              onClick={() => setActiveSection('cards')}
            >
              Cards
            </button>
            <button
              className={activeSection === 'matchups' ? 'active' : ''}
              type="button"
              role="tab"
              aria-selected={activeSection === 'matchups'}
              onClick={() => setActiveSection('matchups')}
            >
              Matchups
            </button>
          </div>
        </div>

        {activeSection === 'cards' ? (
          <div className="card-list" aria-busy={loading}>
            {detail.cards.map((card) => (
              <article className="card-row" key={card.id}>
                <CardIdentity card={card} detail={`Average ${card.avgCopies.toFixed(2)} copies`} />
                <div className="bar-cell">
                  <div className="bar archetype-bar" style={{ width: barWidth(card.inclusionPct, maxInclusion) }} />
                </div>
                <div className="count">
                  <strong>{formatPercent(card.inclusionPct)}</strong>
                  <span>{formatNumber(card.inclusionCount)} decks</span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="card-list" aria-busy={loading}>
            {detail.matchups.map((matchup) => (
              <button
                className="card-row archetype-row"
                type="button"
                key={matchup.opponentId}
                onClick={() => matchup.opponentSlug && onMatchupClick(matchup.opponentSlug)}
              >
                <div className="card-copy">
                  <strong>{matchup.opponentName}</strong>
                  <span>{formatNumber(matchup.games)} games</span>
                </div>
                <div className="bar-cell matchup-cell" aria-label={`${formatPercent(matchup.winRate)} win rate`}>
                  <div className="bar matchup-bar" style={matchupBarStyle(matchup.winRate)} />
                </div>
                <div className="count">
                  <strong>{formatPercent(matchup.winRate)}</strong>
                  <span>{formatNumber(matchup.wins)}-{formatNumber(matchup.losses)}</span>
                </div>
              </button>
            ))}
            {detail.matchups.length === 0 ? (
              <p className="empty-table-note">No matchup rows are available for this archetype yet.</p>
            ) : null}
          </div>
        )}
      </section>
    </main>
  )
}

createRoot(document.getElementById('root')).render(
  <>
    <App />
    <Analytics />
  </>,
)
