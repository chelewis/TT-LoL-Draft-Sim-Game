import { useMutation } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { Champion, GameState, Lane, Player, Side } from '../../api/types'
import { LANES } from '../../api/types'
import { ChampionIcon, LaneIcon, championArt } from '../../components/ChampionArt'
import { ErrorNotice, Pips } from '../../components/common'
import TeamCard from '../../components/TeamCard'
import { useChampions, useCountdown } from '../../hooks/useData'
import { LANE_LABEL, TIER_LABEL, comfortTier, isHidden, isSolo } from '../../lib/format'

interface PoolHint {
  player: string
  lane: Lane
  tier: string
}

const TIER_ORDER = ['BEST', 'COMFORT', 'FAMILIAR']
const TIER_MARK: Record<string, string> = { BEST: '★', COMFORT: '◆', FAMILIAR: '●' }

/** Class filter tabs: label shown -> text matched in the champion's class (the data spells Assassin "Assasin"). */
const CLASS_FILTERS: { label: string; match: string }[] = [
  { label: 'All', match: '' },
  { label: 'Assassin', match: 'Assasin' },
  { label: 'Fighter', match: 'Warrior' },
  { label: 'Mage', match: 'Mage' },
  { label: 'Marksman', match: 'Marksman' },
  { label: 'Support', match: 'Support' },
  { label: 'Tank', match: 'Tank' },
]

const sideName = (s: Side) => (s === 'BLUE' ? 'Blue' : 'Red')

export default function DraftView({ game, onChange }: { game: GameState; onChange: () => void }) {
  const draft = game.draft!
  const solo = isSolo(game)
  // single player: "me" is whichever side is up, so the hints and highlights follow the turn
  const me = solo ? (draft.current_team ?? 'BLUE') : game.you.team
  const champions = useChampions()
  const [selected, setSelected] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [classFilter, setClassFilter] = useState('')
  const seconds = useCountdown(draft.expires_at)

  const myTurn = draft.current_team === me
  const action = draft.action_type
  const used = useMemo(
    () => new Set<number>([...draft.bans.map((b) => b.champion_id), ...draft.blue_picks, ...draft.red_picks]),
    [draft],
  )
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
    for (const list of map.values()) list.sort((a, b) => TIER_ORDER.indexOf(a.tier) - TIER_ORDER.indexOf(b.tier))
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

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (champions.data ?? [])
      .filter((c) => (!q || c.name.toLowerCase().includes(q)) && (!classFilter || c.class.includes(classFilter)))
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [champions.data, query, classFilter])

  const selectedChampion = selected ? byId.get(selected) : undefined
  // the champion I'm hovering shows in my active slot, like the client's pre-lock preview
  const preview = myTurn ? selectedChampion : undefined

  const phaseTitle = draft.current_team
    ? `${sideName(draft.current_team)} ${action === 'PICK' ? 'pick' : 'ban'}`
    : 'Draft complete'
  const phaseSub = myTurn
    ? solo
      ? `${sideName(me)}: choose a champion to ${action === 'PICK' ? 'pick' : 'ban'}`
      : `Your turn: choose a champion to ${action === 'PICK' ? 'pick' : 'ban'}`
    : 'Waiting for your opponent…'

  return (
    <div className="stack">
      <div className={`cs ${action === 'BAN' ? 'cs-ban-phase' : ''}`}>
        <header className="cs-header">
          <SideHeader side="BLUE" game={game} byId={byId} preview={preview} me={me} />
          <div className="cs-phase">
            <div className="cs-phase-title">{phaseTitle}</div>
            {draft.timers_enabled ? (
              <DraftTimer seconds={seconds} startedAt={draft.started_at} expiresAt={draft.expires_at} />
            ) : (
              <div className="cs-timer cs-timer-off">No time limit</div>
            )}
            <div className={`cs-phase-sub ${myTurn ? 'mine' : ''}`}>{phaseSub}</div>
            <div className="cs-steps" aria-label={`Action ${draft.current_action + 1} of ${draft.actions.length}`}>
              {draft.actions.map((a, i) => (
                <span
                  key={i}
                  className={`cs-step ${a.startsWith('BLUE') ? 'blue' : 'red'} ${a.endsWith('BAN') ? 'ban' : 'pick'} ${i < draft.current_action ? 'done' : ''} ${i === draft.current_action ? 'now' : ''}`}
                  title={a.replace('_', ' ').toLowerCase()}
                />
              ))}
            </div>
          </div>
          <SideHeader side="RED" game={game} byId={byId} preview={preview} me={me} />
        </header>

        <div className="cs-body">
          <PickColumn side="BLUE" game={game} byId={byId} preview={preview} me={me} solo={solo} />

          <section className="cs-center" aria-label="Champions">
            <div className="cs-filters">
              <div className="cs-tabs" role="tablist" aria-label="Filter by class">
                {CLASS_FILTERS.map((f) => (
                  <button
                    key={f.label}
                    role="tab"
                    aria-selected={classFilter === f.match}
                    className={`cs-tab ${classFilter === f.match ? 'active' : ''}`}
                    onClick={() => setClassFilter(f.match)}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <input
                className="cs-search"
                placeholder="Search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search champions"
              />
            </div>
            <div className="cs-grid-scroll">
              <div className="cs-grid">
                {visible.map((c) => {
                  const isUsed = used.has(c.id)
                  const best = hints.get(c.id)?.[0]
                  return (
                    <button
                      key={c.id}
                      className={`cs-champ ${selected === c.id ? 'selected' : ''} ${isUsed ? 'used' : ''}`}
                      disabled={isUsed}
                      onClick={() => setSelected(c.id)}
                      onDoubleClick={() => myTurn && !isUsed && !act.isPending && act.mutate(c.id)}
                      title={`${c.name} · ${c.class}${best ? ` · ${best.player} (${LANE_LABEL[best.lane]}): ${TIER_LABEL[best.tier]}` : ''}`}
                    >
                      <span className="cs-champ-frame">
                        <ChampionIcon champion={c} size={64} />
                        {best && (
                          <span className={`cs-comfort tier-${best.tier.toLowerCase()}`} aria-label={TIER_LABEL[best.tier]}>
                            {TIER_MARK[best.tier]}
                          </span>
                        )}
                      </span>
                      <span className="cs-champ-name">{c.name}</span>
                    </button>
                  )
                })}
                {visible.length === 0 && <p className="muted">No champions match.</p>}
              </div>
            </div>
          </section>

          <PickColumn side="RED" game={game} byId={byId} preview={preview} me={me} solo={solo} />
        </div>

        <footer className="cs-footer">
          <ChampionDetail champion={selectedChampion} hints={selectedChampion ? hints.get(selectedChampion.id) : undefined} />
          <div className="cs-lock">
            <ErrorNotice error={act.error} />
            <button
              className={`cs-lock-in ${action === 'BAN' ? 'ban' : ''}`}
              disabled={!myTurn || !selected || act.isPending}
              onClick={() => selected && act.mutate(selected)}
            >
              {action === 'BAN' ? 'Ban' : 'Lock in'}
            </button>
          </div>
        </footer>
      </div>

      <div className="grid two">
        <TeamCard team={game.teams.BLUE} side="BLUE" you={me === 'BLUE'} />
        <TeamCard team={game.teams.RED} side="RED" you={me === 'RED'} />
      </div>
    </div>
  )
}

function DraftTimer({ seconds, startedAt, expiresAt }: { seconds: number; startedAt: string | null; expiresAt: string | null }) {
  const total = startedAt && expiresAt ? Math.max(1, (Date.parse(expiresAt) - Date.parse(startedAt)) / 1000) : 30
  const fraction = Math.max(0, Math.min(1, seconds / total))
  const level = seconds <= 5 ? 'critical' : seconds <= 10 ? 'warning' : 'ok'
  return (
    <div className={`cs-timer ${level}`} role="timer" aria-label={`${seconds} seconds remaining`}>
      <div className="cs-timer-number">{seconds}</div>
      <div className="cs-timer-track" aria-hidden="true">
        <div className="cs-timer-fill" style={{ width: `${fraction * 100}%` }} />
      </div>
    </div>
  )
}

interface SideProps {
  side: Side
  game: GameState
  byId: Map<number, Champion>
  preview: Champion | undefined
  me: Side
}

/** Index of the slot (pick or ban) this side is filling right now, or -1. */
function activeSlot(game: GameState, side: Side, kind: 'PICK' | 'BAN'): number {
  const draft = game.draft!
  if (draft.current_team !== side || draft.action_type !== kind) return -1
  return kind === 'PICK'
    ? (side === 'BLUE' ? draft.blue_picks : draft.red_picks).length
    : draft.bans.filter((b) => b.team === side).length
}

function SideHeader({ side, game, byId, preview, me }: SideProps) {
  const draft = game.draft!
  const banSlots = draft.actions.filter((a) => a === `${side}_BAN`).length
  const bans = draft.bans.filter((b) => b.team === side)
  const now = activeSlot(game, side, 'BAN')
  const team = game.teams[side]
  return (
    <div className={`cs-side-header ${side.toLowerCase()}`}>
      <div className="cs-team-name">
        {team?.name ?? `${sideName(side)} team`}
        {me === side && <span className="cs-you">{isSolo(game) ? 'up now' : 'you'}</span>}
      </div>
      {banSlots > 0 && (
        <div className="cs-bans" aria-label={`${sideName(side)} bans`}>
          {Array.from({ length: banSlots }, (_, i) => {
            const champ = bans[i] ? byId.get(bans[i].champion_id) : i === now && side === me ? preview : undefined
            return (
              <span key={i} className={`cs-ban ${bans[i] ? 'filled' : ''} ${i === now ? 'now' : ''}`} title={champ?.name}>
                {champ && <ChampionIcon champion={champ} size={36} />}
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}

function PickColumn({ side, game, byId, preview, me, solo }: SideProps & { solo: boolean }) {
  const draft = game.draft!
  const picks = side === 'BLUE' ? draft.blue_picks : draft.red_picks
  const pickSlots = draft.actions.filter((a) => a === `${side}_PICK`).length
  const now = activeSlot(game, side, 'PICK')
  const roster = game.teams[side]?.roster
  return (
    <aside className={`cs-picks ${side.toLowerCase()}`} aria-label={`${sideName(side)} picks`}>
      {Array.from({ length: pickSlots }, (_, i) => {
        const locked = picks[i] !== undefined ? byId.get(picks[i]) : undefined
        const hovering = !locked && i === now && side === me ? preview : undefined
        const champ = locked ?? hovering
        return (
          <div
            key={i}
            className={`cs-slot ${locked ? 'locked' : ''} ${hovering ? 'hovering' : ''} ${i === now ? 'now' : ''}`}
            style={{ backgroundImage: championArt(champ) }}
          >
            <div className="cs-slot-text">
              <span className="cs-slot-label">
                {i === now ? (solo || side === me ? 'Picking…' : 'Opponent picking…') : `Pick ${i + 1}`}
              </span>
              <span className="cs-slot-champ">{champ?.name ?? ''}</span>
            </div>
          </div>
        )
      })}
      {roster && (
        <ul className="cs-roster" aria-label={`${sideName(side)} roster`}>
          {LANES.map((lane) => (
            <li key={lane} title={LANE_LABEL[lane]}>
              <LaneIcon lane={lane} size={16} />
              <span>{roster[lane]?.name ?? '—'}</span>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}

function ChampionDetail({ champion: c, hints }: { champion: Champion | undefined; hints?: PoolHint[] }) {
  if (!c) return <div className="cs-detail muted">Select a champion to see its stats. Double-click to lock in.</div>
  return (
    <div className="cs-detail">
      <ChampionIcon champion={c} size={56} className="cs-detail-icon" />
      <div className="stack cs-detail-body">
        <div className="cs-detail-head">
          <strong>{c.name}</strong>
          <span className="muted small">
            {c.class.replace(/Assasin/g, 'Assassin')} · difficulty {c.difficulty} ·{' '}
            {c.damage_type === 'P' ? 'physical' : c.damage_type === 'M' ? 'magic' : 'mixed'} damage · WR {c.win_rate}% · PR {c.pick_rate}%
          </span>
        </div>
        <div className="cs-detail-stats small">
          <span>Damage <Pips value={c.damage} /></span>
          <span>Sturdiness <Pips value={c.sturdiness} /></span>
          <span>CC <Pips value={c.crowd_control} /></span>
          <span>Mobility <Pips value={c.mobility} /></span>
          <span>Utility <Pips value={c.utility} /></span>
        </div>
        <span className="small muted">
          Strong as {c.strength.toLowerCase()}, vulnerable to {c.weakness.toLowerCase()}
          {hints && hints.length > 0 && (
            <>
              {' · '}
              <span className="cs-detail-pool">In pools: {hints.map((h) => `${h.player} (${TIER_LABEL[h.tier]})`).join(', ')}</span>
            </>
          )}
        </span>
      </div>
    </div>
  )
}
