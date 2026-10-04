import { useMutation } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { GameState, Lane, Player, Side } from '../../api/types'
import { ChampionIcon, LaneIcon } from '../../components/ChampionArt'
import { LANES } from '../../api/types'
import { ErrorNotice } from '../../components/common'
import { OverBudgetBadge } from '../../components/TeamCard'
import { useChampionMap } from '../../hooks/useData'
import { LANE_LABEL, TIER_LABEL, TIER_MODIFIER, comfortTier, isHidden, isSolo } from '../../lib/format'

type Assignment = Partial<Record<Lane, number>>

/**
 * Lane assignment. Desktop: drag a champion onto a player. Mobile (and keyboard): tap a champion,
 * then tap a lane. Both end in the same API call, so the backend does not depend on either style.
 */
function LineupEditor({ game, side: me, onChange }: { game: GameState; side: Side; onChange: () => void }) {
  const solo = isSolo(game)
  const sideName = me === 'BLUE' ? 'Blue' : 'Red'
  const champions = useChampionMap()
  const picks = me === 'BLUE' ? game.draft!.blue_picks : game.draft!.red_picks
  const myTeam = game.teams[me]
  const myUser = me === 'BLUE' ? game.players.blue : game.players.red
  const opponentUser = me === 'BLUE' ? game.players.red : game.players.blue
  const confirmed = !!myUser?.lineup_ready

  // multiplayer: your own lineup; single player: the lineup of the side this editor is for
  const server = (solo ? game.lineup?.[me === 'BLUE' ? 'blue' : 'red'] : game.lineup?.yours) as Assignment | undefined
  const [assignment, setAssignment] = useState<Assignment>(() => server ?? {})
  const [selected, setSelected] = useState<number | null>(null)
  useEffect(() => {
    setAssignment(server ?? {})
  }, [server])

  const save = useMutation({
    mutationFn: (next: Assignment) =>
      api(`/games/${game.game_id}/lineup`, {
        method: 'PUT',
        body: { assignments: Object.entries(next).map(([lane, champion_id]) => ({ lane, champion_id })), side: solo ? me : undefined },
      }),
    onSuccess: onChange,
    onError: onChange,
  })
  const confirm = useMutation({
    mutationFn: () => api(`/games/${game.game_id}/lineup/ready${solo ? `?side=${me}` : ''}`, { method: 'POST' }),
    onSuccess: onChange,
  })

  function assign(lane: Lane, championId: number) {
    const next: Assignment = { ...assignment }
    // a champion occupies one lane only: remove it from wherever it was
    for (const l of LANES) if (next[l] === championId) delete next[l]
    next[lane] = championId
    setAssignment(next)
    setSelected(null)
    save.mutate(next)
  }

  function clear(lane: Lane) {
    const next = { ...assignment }
    delete next[lane]
    setAssignment(next)
    save.mutate(next)
  }

  const assigned = new Set(Object.values(assignment))
  const complete = LANES.every((l) => assignment[l] !== undefined)
  const roster = myTeam?.roster
  const tiers = useMemo(() => {
    const out: Partial<Record<Lane, string>> = {}
    for (const lane of LANES) {
      const p = roster?.[lane]
      const cid = assignment[lane]
      if (p && !isHidden(p) && cid !== undefined) out[lane] = comfortTier((p as Player).pool, cid)
    }
    return out
  }, [roster, assignment])

  return (
    <div className="stack">
      <div className="card row between wrap">
        <div>
          <h2>{solo ? `Assign ${sideName}'s champions` : 'Assign your champions'}</h2>
          <p className="muted">
            Give each drafted champion to one of your players. Champions in a player's pool perform better.{' '}
            {myTeam && <OverBudgetBadge team={myTeam} />}
          </p>
        </div>
        <div className="small muted">
          <div>{solo ? sideName : 'You'}: {confirmed ? <span className="badge ok">confirmed</span> : <span className="badge">assigning</span>}</div>
          {!solo && (
            <div>
              {opponentUser?.username ?? 'Opponent'}:{' '}
              {opponentUser?.lineup_ready ? <span className="badge ok">confirmed</span> : <span className="badge">assigning</span>}
            </div>
          )}
        </div>
      </div>

      <ErrorNotice error={save.error ?? confirm.error} />

      <div className="card stack">
        <h3>Drafted champions</h3>
        <div className="row wrap">
          {picks.map((id) => {
            const c = champions.get(id)
            const placed = assigned.has(id)
            return (
              <button
                key={id}
                draggable={!confirmed}
                onDragStart={(e) => e.dataTransfer.setData('text/plain', String(id))}
                className={`champ-card ${selected === id ? 'selected' : ''} ${placed ? 'placed' : ''}`}
                disabled={confirmed}
                onClick={() => setSelected(selected === id ? null : id)}
              >
                <ChampionIcon champion={c} size={56} />
                <strong>{c?.name ?? id}</strong>
                <span className="muted small">{placed ? 'assigned' : 'tap, then pick a lane'}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="lane-slots">
        {LANES.map((lane) => {
          const p = roster?.[lane]
          const player = p && !isHidden(p) ? (p as Player) : null
          const cid = assignment[lane]
          const tier = tiers[lane]
          return (
            <div
              key={lane}
              className={`card lane-slot ${selected ? 'droppable' : ''}`}
              onDragOver={(e) => !confirmed && e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault()
                if (!confirmed) assign(lane, Number(e.dataTransfer.getData('text/plain')))
              }}
              onClick={() => !confirmed && selected && assign(lane, selected)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if ((e.key === 'Enter' || e.key === ' ') && selected && !confirmed) assign(lane, selected)
              }}
              aria-label={`${LANE_LABEL[lane]} slot`}
            >
              <div className="row between">
                <strong className="row"><LaneIcon lane={lane} />{LANE_LABEL[lane]}</strong>
                <span className="muted small">{player?.name}</span>
              </div>
              {player && (
                <p className="small muted">
                  Agg {player.aggr} · Awr {player.aware} · Pos {player.pos} · Dmg {player.dmg} · CS {player.cs}
                </p>
              )}
              {cid !== undefined ? (
                <div className="assigned">
                  <strong className="row"><ChampionIcon champion={champions.get(cid)} size={40} />{champions.get(cid)?.name}</strong>
                  {tier && (
                    <span className={`badge tier-${tier.toLowerCase()}`}>
                      {TIER_LABEL[tier]} {TIER_MODIFIER[tier] > 0 ? '+' : ''}
                      {TIER_MODIFIER[tier]}%
                    </span>
                  )}
                  {!confirmed && (
                    <button
                      className="ghost small"
                      onClick={(e) => {
                        e.stopPropagation()
                        clear(lane)
                      }}
                    >
                      Remove
                    </button>
                  )}
                </div>
              ) : (
                <p className="muted">{selected ? 'Tap to place here' : 'Drop a champion here'}</p>
              )}
            </div>
          )
        })}
      </div>

      <div className={solo ? 'row' : 'sticky-actions'}>
        <button className="primary" disabled={!complete || confirmed || confirm.isPending} onClick={() => confirm.mutate()}>
          {confirmed ? (solo ? 'Confirmed' : 'Waiting for opponent…') : complete ? `Confirm ${solo ? `${sideName} ` : ''}lineup` : 'Assign all five lanes'}
        </button>
      </div>
    </div>
  )
}

/** Multiplayer: one lineup. Single player: the Blue and Red lineups, one after the other. */
export default function LineupView({ game, onChange }: { game: GameState; onChange: () => void }) {
  if (!isSolo(game)) return <LineupEditor game={game} side={game.you.team} onChange={onChange} />
  return (
    <div className="stack">
      <div className="notice">Single player: assign and confirm both lineups. The match is simulated as soon as both are confirmed.</div>
      <LineupEditor game={game} side="BLUE" onChange={onChange} />
      <LineupEditor game={game} side="RED" onChange={onChange} />
    </div>
  )
}
