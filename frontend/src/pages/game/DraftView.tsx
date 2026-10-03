import { useMutation } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { Champion, GameState, Lane, Player, Side } from '../../api/types'
import { LANES } from '../../api/types'
import { ChampionTag, ErrorNotice, Pips } from '../../components/common'
import TeamCard from '../../components/TeamCard'
import { useChampions, useCountdown } from '../../hooks/useData'
import { LANE_LABEL, TIER_LABEL, comfortTier, isHidden, isSolo } from '../../lib/format'

interface PoolHint {
  player: string
  lane: Lane
  tier: string
}

export default function DraftView({ game, onChange }: { game: GameState; onChange: () => void }) {
  const draft = game.draft!
  const solo = isSolo(game)
  // single player: "me" is whichever side is up, so the hints, glow and cards follow the turn
  const me = solo ? (draft.current_team ?? 'BLUE') : game.you.team
  const champions = useChampions()
  const [selected, setSelected] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [role, setRole] = useState('')
  const seconds = useCountdown(draft.expires_at)
  const myTurnNow = draft.current_team === me

  const myTurn = draft.current_team === me
  const action = draft.action_type
  const used = useMemo(() => {
    const ids = new Set<number>([...draft.bans.map((b) => b.champion_id), ...draft.blue_picks, ...draft.red_picks])
    return ids
  }, [draft])
  const byId = useMemo(() => new Map((champions.data ?? []).map((c) => [c.id, c])), [champions.data])

  // Which of my players have a champion in their pool (comfort hint). Only my own data is ever used.
  const hints = useMemo(() => {
    const map = new Map<number, PoolHint[]>()
    const myTeam = game.teams[me]
    if (!myTeam) return map
    for (const lane of LANES) {
      const p = myTeam.roster[lane]
      if (!p || isHidden(p)) continue
      const player = p as Player
      player.pool.forEach((cid) => {
        const list = map.get(cid) ?? []
        list.push({ player: player.name, lane, tier: comfortTier(player.pool, cid) })
        map.set(cid, list)
      })
    }
    return map
  }, [game.teams, me])

  const act = useMutation({
    mutationFn: (championId: number) =>
      api(`/games/${game.game_id}/draft/${action === 'PICK' ? 'pick' : 'ban'}`, { body: { champion_id: championId } }),
    onSuccess: () => {
      setSelected(null)
      onChange()
    },
    onError: onChange,
  })

  const roles = useMemo(() => [...new Set((champions.data ?? []).map((c) => c.class.split('-')[0]))].sort(), [champions.data])
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (champions.data ?? []).filter(
      (c) => (!q || c.name.toLowerCase().includes(q)) && (!role || c.class.startsWith(role) || c.class.includes(role)),
    )
  }, [champions.data, query, role])

  const selectedChampion = selected ? byId.get(selected) : undefined

  return (
    <div className="stack">
      <div className={`card draft-bar ${myTurn ? 'my-turn' : ''}`}>
        <div>
          {myTurn && <div className="turn-flag">{solo ? `${me === 'BLUE' ? 'Blue' : 'Red'}'s turn to` : 'Your turn to'} {action === 'PICK' ? 'pick' : 'ban'}!</div>}
          <h2>
            {draft.current_team === 'BLUE' ? 'Blue' : 'Red'} {action === 'PICK' ? 'picks' : 'bans'}
          </h2>
          <p className="muted">
            {myTurn
              ? solo
                ? `Choose a champion for ${me === 'BLUE' ? 'Blue' : 'Red'} to ${action === 'PICK' ? 'pick' : 'ban'}.`
                : `Your turn: choose a champion to ${action === 'PICK' ? 'pick' : 'ban'}.`
              : 'Waiting for your opponent…'}{' '}
            <span className="small">
              Action {draft.current_action + 1} / {draft.actions.length}
            </span>
          </p>
        </div>
        {draft.timers_enabled ? (
          <DraftTimer seconds={seconds} startedAt={draft.started_at} expiresAt={draft.expires_at} active={myTurn} />
        ) : (
          <div className="muted">No time limit</div>
        )}
      </div>

      <div className="steps" aria-label="Draft progress">
        {draft.actions.map((a, i) => (
          <span key={i} className={`step ${a.startsWith('BLUE') ? 'blue' : 'red'} ${i < draft.current_action ? 'done' : ''} ${i === draft.current_action ? 'now' : ''}`} title={a.replace('_', ' ')}>
            {a.endsWith('BAN') ? '✕' : '●'}
          </span>
        ))}
      </div>

      <div className="grid two">
        <SidePanel side="BLUE" game={game} byId={byId} mine={me === 'BLUE'} solo={solo} />
        <SidePanel side="RED" game={game} byId={byId} mine={me === 'RED'} solo={solo} />
      </div>

      <div className={`card stack ${myTurnNow ? 'turn-glow' : ''}`}>
        <div className="row wrap">
          <input placeholder="Search champions" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search champions" />
          <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Filter by class">
            <option value="">All classes</option>
            {roles.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </div>
        <ErrorNotice error={act.error} />
        <div className={`champ-grid ${action === 'BAN' ? 'ban-phase' : ''}`}>
          {visible.map((c) => {
            const isUsed = used.has(c.id)
            const hint = hints.get(c.id)
            const best = hint?.sort((a, b) => ['BEST', 'COMFORT', 'FAMILIAR'].indexOf(a.tier) - ['BEST', 'COMFORT', 'FAMILIAR'].indexOf(b.tier))[0]
            return (
              <button
                key={c.id}
                className={`champ-card ${selected === c.id ? 'selected' : ''} ${isUsed ? 'used' : ''}`}
                disabled={isUsed}
                onClick={() => setSelected(c.id)}
                title={`${c.class} · ${c.strength}`}
              >
                <strong>{c.name}</strong>
                <span className="muted small">{c.class}</span>
                {best && (
                  <span className={`badge tier-${best.tier.toLowerCase()}`} title={`${best.player} (${LANE_LABEL[best.lane]}): ${TIER_LABEL[best.tier]}`}>
                    {best.player.split(' ')[0]}: {TIER_LABEL[best.tier]}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {selectedChampion && <ChampionDetail champion={selectedChampion} hints={hints.get(selectedChampion.id)} />}

      <div className="sticky-actions">
        <button
          className="primary"
          disabled={!myTurn || !selected || act.isPending}
          onClick={() => selected && act.mutate(selected)}
        >
          {selectedChampion ? `${action === 'PICK' ? 'Lock in' : 'Ban'} ${selectedChampion.name}` : 'Select a champion'}
        </button>
      </div>

      <div className="grid two">
        <TeamCard team={game.teams.BLUE} side="BLUE" you={me === 'BLUE'} />
        <TeamCard team={game.teams.RED} side="RED" you={me === 'RED'} />
      </div>
    </div>
  )
}

function DraftTimer({ seconds, startedAt, expiresAt, active }: { seconds: number; startedAt: string | null; expiresAt: string | null; active: boolean }) {
  const total = startedAt && expiresAt ? Math.max(1, (Date.parse(expiresAt) - Date.parse(startedAt)) / 1000) : 30
  const fraction = Math.max(0, Math.min(1, seconds / total))
  const level = seconds <= 5 ? 'critical' : seconds <= 10 ? 'warning' : 'ok'
  return (
    <div className={`big-timer ${level} ${active ? 'active' : ''}`} role="timer" aria-label={`${seconds} seconds remaining`}>
      <div className="big-timer-number">{seconds}</div>
      <div className="big-timer-label">seconds</div>
      <div className="big-timer-track" aria-hidden="true">
        <div className="big-timer-fill" style={{ width: `${fraction * 100}%` }} />
      </div>
    </div>
  )
}

function SidePanel({ side, game, byId, mine, solo }: { side: Side; game: GameState; byId: Map<number, Champion>; mine: boolean; solo: boolean }) {
  const draft = game.draft!
  const picks = side === 'BLUE' ? draft.blue_picks : draft.red_picks
  const bans = draft.bans.filter((b) => b.team === side)
  return (
    <div
      className={`card side-${side.toLowerCase()} ${mine ? 'is-you' : ''} ${mine && draft.current_team === side ? 'turn-glow' : ''}`}
    >
      <h3>
        {side === 'BLUE' ? 'Blue' : 'Red'} draft {mine && <span className="badge you-badge">{solo ? 'UP NOW' : 'YOU'}</span>}
      </h3>
      <p className="small muted">Bans</p>
      <div className="row wrap">
        {bans.length === 0 && <span className="muted">—</span>}
        {bans.map((b) => (
          <span key={b.champion_id} className="chip banned">
            <ChampionTag champion={byId.get(b.champion_id)} />
          </span>
        ))}
      </div>
      <p className="small muted">Picks</p>
      <div className="row wrap">
        {picks.length === 0 && <span className="muted">—</span>}
        {picks.map((id) => (
          <span key={id} className="chip">
            <ChampionTag champion={byId.get(id)} />
          </span>
        ))}
      </div>
    </div>
  )
}

function ChampionDetail({ champion: c, hints }: { champion: Champion; hints?: PoolHint[] }) {
  return (
    <div className="card champ-detail">
      <div className="row between wrap">
        <h3>{c.name}</h3>
        <span className="muted">
          {c.class} · difficulty {c.difficulty} · {c.damage_type === 'P' ? 'physical' : c.damage_type === 'M' ? 'magic' : 'mixed'} damage
        </span>
      </div>
      <div className="stats-grid">
        <span>Damage <Pips value={c.damage} /></span>
        <span>Sturdiness <Pips value={c.sturdiness} /></span>
        <span>Crowd control <Pips value={c.crowd_control} /></span>
        <span>Mobility <Pips value={c.mobility} /></span>
        <span>Utility <Pips value={c.utility} /></span>
      </div>
      <p className="small muted">
        Strong as {c.strength.toLowerCase()}, vulnerable to {c.weakness.toLowerCase()} · win rate {c.win_rate}% · pick rate {c.pick_rate}%
      </p>
      {hints && hints.length > 0 && (
        <p className="small">
          In pools: {hints.map((h) => `${h.player} (${TIER_LABEL[h.tier]})`).join(', ')}
        </p>
      )}
    </div>
  )
}
