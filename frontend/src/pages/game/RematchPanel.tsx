import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { GameState, Side } from '../../api/types'
import { ErrorNotice } from '../../components/common'
import { isCpu, isSolo } from '../../lib/format'

/** After a finished match (or series): both sides click Rematch, then everyone moves to a new lobby with the same
 * settings, teams and sides. Single player and vs CPU need one click. */
export default function RematchPanel({ game, names }: { game: GameState; names: Record<Side, string> }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const r = game.rematch!
  const onePlayer = isSolo(game) || isCpu(game)
  const mine = onePlayer ? r.ready.blue && r.ready.red : game.you.team === 'BLUE' ? r.ready.blue : r.ready.red
  const ready = useMutation({
    mutationFn: (value: boolean) => api<GameState>(`/games/${game.game_id}/rematch`, { body: { ready: value } }),
    onSuccess: (state) => {
      qc.invalidateQueries({ queryKey: ['game', game.game_id] })
      // the socket also announces it, but the player who completed the rematch shouldn't depend on that
      if (state.rematch?.game_id) navigate(`/game/${state.rematch.game_id}`)
    },
  })

  if (r.game_id) {
    return (
      <div className="card row between wrap">
        <span>The rematch has started.</span>
        <Link to={`/game/${r.game_id}`}>Continue to the rematch →</Link>
      </div>
    )
  }
  return (
    <div className="card stack">
      <h2>{onePlayer ? 'Play again' : 'Rematch'}</h2>
      <p className="muted">Same settings, teams and sides. You'll land in the ready check and can still change them.</p>
      {!onePlayer && (
        <div className="row wrap">
          {(['BLUE', 'RED'] as Side[]).map((x) => (
            <span key={x}>
              <strong>{names[x]}</strong>{' '}
              {r.ready[x === 'BLUE' ? 'blue' : 'red'] ? <span className="badge ok">wants a rematch</span> : <span className="badge">not yet</span>}
            </span>
          ))}
        </div>
      )}
      <ErrorNotice error={ready.error} />
      <div className="row wrap">
        <button className={mine ? 'ghost' : 'primary'} disabled={ready.isPending} onClick={() => ready.mutate(!mine)}>
          {onePlayer ? 'Play again' : mine ? 'Cancel rematch' : 'Rematch'}
        </button>
        {mine && !onePlayer && <span className="muted">Waiting for the other player…</span>}
      </div>
    </div>
  )
}
