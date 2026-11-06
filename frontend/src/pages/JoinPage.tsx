import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { LobbySummary } from '../api/types'
import { ErrorNotice, Loading } from '../components/common'

/** Opened from a lobby invite link (/join/CODE): joins the lobby straight away, then goes to the game. */
export default function JoinPage() {
  const code = (useParams().code ?? '').trim().toUpperCase()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const started = useRef(false)
  const join = useMutation({
    mutationFn: () => api<LobbySummary>(`/lobbies/${encodeURIComponent(code)}/join`, { method: 'POST' }),
    onSuccess: (lobby) => {
      qc.invalidateQueries({ queryKey: ['my-games'] })
      navigate(`/game/${lobby.game_id}`, { replace: true })
    },
  })

  useEffect(() => {
    // StrictMode runs effects twice in development; join only once
    if (started.current) return
    started.current = true
    join.mutate()
  }, [join])

  if (join.isError) {
    return (
      <div className="card stack">
        <h2>Couldn't join lobby {code}</h2>
        <ErrorNotice error={join.error} />
        <Link to="/">Back to Play</Link>
      </div>
    )
  }
  return <Loading label={`Joining lobby ${code}…`} />
}
