import { useCallback, useRef } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import type { MatchupKind } from '../../api/types'
import MatchupMatrix from './MatchupMatrix'
import { ADMIN_HOME } from './nav'

const MATRICES: { slug: string; label: string; kind: MatchupKind }[] = [
  { slug: 'same-team', label: 'Same team', kind: 'ally' },
  { slug: 'against-team', label: 'Against team', kind: 'enemy' },
]

export default function WinratesPage() {
  const { matrix } = useParams()
  const navigate = useNavigate()
  const dirty = useRef(false)
  const onDirtyChange = useCallback((value: boolean) => { dirty.current = value }, [])

  const current = MATRICES.find((m) => m.slug === matrix)
  if (!current) return <Navigate to={`${ADMIN_HOME}/${MATRICES[0].slug}`} replace />

  const open = (slug: string) => {
    if (slug === current.slug) return
    if (dirty.current && !window.confirm('You have unsaved changes in this matrix. Leave without saving?')) return
    dirty.current = false
    navigate(`${ADMIN_HOME}/${slug}`)
  }

  return (
    <div className="stack">
      <h1>Champion win rates</h1>
      <div className="tabs admin-tabs" role="tablist" aria-label="Win rate matrix">
        {MATRICES.map((m) => (
          <button key={m.slug} role="tab" aria-selected={m.slug === current.slug} className={m.slug === current.slug ? 'active' : ''} onClick={() => open(m.slug)}>
            {m.label}
          </button>
        ))}
      </div>
      <MatchupMatrix key={current.kind} kind={current.kind} onDirtyChange={onDirtyChange} />
    </div>
  )
}
