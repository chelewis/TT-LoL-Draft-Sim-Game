import { useMutation } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { Champion, GameState, HiddenPlayer, Lane, Player, Side } from '../../api/types'
import { LANES } from '../../api/types'
import { ChampionIcon, LaneIcon, championArt } from '../../components/ChampionArt'
import { ErrorNotice, Pips } from '../../components/common'
import ChatPanel from '../../components/ChatPanel'
import TeamCard from '../../components/TeamCard'
import { useCountdownTick } from '../../hooks/useCountdownTick'
import { useChampions, useCountdown } from '../../hooks/useData'
import { useTurnAlert } from '../../hooks/useTurnAlert'
import { alertsState, disableAlerts, enableAlerts, turnAlertKey } from '../../lib/alerts'
import { LANE_LABEL, TIER_LABEL, TIER_MODIFIER, comfortTier, isHidden, isSolo, rankLabel } from '../../lib/format'
import { lineupAssignments, swapLanes, type Lineup, type SwapKind } from '../../lib/lineup'
import { isSoundOn, playSound, setSoundOn } from '../../lib/sound'

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
    // resolves to the action that was taken: by the time it succeeds, `action` may already be the next one
    mutationFn: async (championId: number) => {
      const taken = action
      await api(`/games/${game.game_id}/draft/${taken === 'PICK' ? 'pick' : 'ban'}`, { body: { champion_id: championId } })
      return taken
    },
    onSuccess: (taken) => {
      playSound(taken === 'BAN' ? 'ban' : 'lock')
      setSelected(null)
      onChange()
    },
    onError: onChange,
  })

  // ----- finalization: after the last pick, each side swaps champions or positions, then locks in
  const finalizing = draft.complete
  const editing = game.status === 'LANE_ASSIGNMENT'
  const [swapMenu, setSwapMenu] = useState<{ side: Side; lane: Lane } | null>(null)
  const lineups = useMemo(() => ({ BLUE: lineupOf(game, 'BLUE'), RED: lineupOf(game, 'RED') }), [game])
  const isReady = (side: Side) => !!(side === 'BLUE' ? game.players.blue : game.players.red)?.lineup_ready
  const canEdit = (side: Side) => finalizing && editing && (solo || side === game.you.team) && !!lineups[side] && !isReady(side)

  const saveLineup = useMutation({
    mutationFn: ({ side, lineup }: { side: Side; lineup: Lineup }) =>
      api(`/games/${game.game_id}/lineup`, { method: 'PUT', body: { assignments: lineupAssignments(lineup), side: solo ? side : undefined } }),
    onSuccess: () => {
      playSound('swap')
      onChange()
    },
    onError: onChange,
  })
  const lockLineup = useMutation({
    mutationFn: (side: Side) => api(`/games/${game.game_id}/lineup/ready${solo ? `?side=${side}` : ''}`, { method: 'POST' }),
    onSuccess: () => {
      playSound('lock')
      onChange()
    },
    onError: onChange,
  })

  // ----- sound and "your turn" alerts
  const [soundOn, setSoundOnState] = useState(isSoundOn)
  const [alerts, setAlerts] = useState(alertsState)
  useTurnAlert(
    turnAlertKey({ solo, myTurn: !finalizing && myTurn, canFinalize: canEdit(game.you.team) }),
    finalizing ? 'Finalize your lineup' : `Your turn to ${action === 'PICK' ? 'pick' : 'ban'}`,
  )

  useCountdownTick(draft.expires_at, draft.timers_enabled && !finalizing && myTurn)

  // buzzer when the timer ran out on me and the server acted for me
  const seenHistory = useRef(draft.history.length)
  useEffect(() => {
    const fresh = draft.history.slice(seenHistory.current)
    seenHistory.current = draft.history.length
    if (fresh.some((h) => h.auto && (solo || h.team === game.you.team))) playSound('buzzer')
  }, [draft.history, solo, game.you.team])

  function toggleSound() {
    setSoundOn(!soundOn)
    setSoundOnState(!soundOn)
    if (!soundOn) playSound('select')
  }

  function swap(side: Side, a: Lane, b: Lane, kind: SwapKind) {
    const current = lineups[side]
    if (!current) return
    setSwapMenu(null)
    saveLineup.mutate({ side, lineup: swapLanes(current, a, b, kind) })
  }

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (champions.data ?? [])
      .filter((c) => (!q || c.name.toLowerCase().includes(q)) && (!classFilter || c.class.includes(classFilter)))
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [champions.data, query, classFilter])

  const selectedChampion = selected ? byId.get(selected) : undefined
  // the champion I'm hovering shows in my active slot, like the client's pre-lock preview
  const preview = myTurn ? selectedChampion : undefined

  const editableSides: Side[] = (solo ? (['BLUE', 'RED'] as Side[]) : [game.you.team]).filter((s) => lineups[s])
  const phaseTitle = finalizing
    ? editing ? 'Finalization' : 'Simulating match…'
    : draft.current_team
      ? `${sideName(draft.current_team)} ${action === 'PICK' ? 'pick' : 'ban'}`
      : 'Draft complete'
  const phaseSub = finalizing
    ? !editing
      ? 'Both lineups are locked in.'
      : editableSides.some(canEdit)
        ? 'Swap champions or positions with the ⇅ buttons, then lock in your lineup.'
        : 'Waiting for your opponent to lock in…'
    : myTurn
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
            {finalizing ? (
              <div className="cs-timer cs-timer-off">
                {(['BLUE', 'RED'] as Side[]).map((s) => (
                  <span key={s} className={`cs-ready ${s.toLowerCase()} ${isReady(s) ? 'done' : ''}`}>
                    {sideName(s)}: {isReady(s) ? 'locked in' : 'finalizing'}
                  </span>
                ))}
              </div>
            ) : draft.timers_enabled ? (
              <DraftTimer seconds={seconds} startedAt={draft.started_at} expiresAt={draft.expires_at} />
            ) : (
              <div className="cs-timer cs-timer-off">No time limit</div>
            )}
            <div className={`cs-phase-sub ${myTurn || editableSides.some(canEdit) ? 'mine' : ''}`}>{phaseSub}</div>
            <div className="cs-steps" aria-label={`Action ${draft.current_action + 1} of ${draft.actions.length}`}>
              {draft.actions.map((a, i) => (
                <span
                  key={i}
                  className={`cs-step ${a.startsWith('BLUE') ? 'blue' : 'red'} ${a.endsWith('BAN') ? 'ban' : 'pick'} ${i < draft.current_action ? 'done' : ''} ${i === draft.current_action ? 'now' : ''}`}
                  title={a.replace('_', ' ').toLowerCase()}
                />
              ))}
            </div>
            <div className="cs-alerts">
              <button className="cs-alert-toggle" aria-pressed={soundOn} onClick={toggleSound}>
                {soundOn ? '🔊 Sound on' : '🔇 Sound off'}
              </button>
              {!solo && alerts !== 'unsupported' && (
                <button
                  className="cs-alert-toggle"
                  aria-pressed={alerts === 'on'}
                  disabled={alerts === 'blocked'}
                  onClick={() => (alerts === 'on' ? setAlerts(disableAlerts()) : enableAlerts().then(setAlerts))}
                  title={
                    alerts === 'blocked'
                      ? 'Notifications are blocked for this site. Allow them in your browser’s site settings.'
                      : 'Get a desktop notification when it is your turn and you are in another tab or window'
                  }
                >
                  {alerts === 'on' ? '🔔 Turn alerts on' : alerts === 'blocked' ? '🔕 Turn alerts blocked' : '🔕 Turn alerts off'}
                </button>
              )}
            </div>
          </div>
          <SideHeader side="RED" game={game} byId={byId} preview={preview} me={me} />
        </header>

        <div className={`cs-body ${solo ? '' : 'with-chat'}`}>
          <PickColumn
            side="BLUE"
            game={game}
            byId={byId}
            preview={preview}
            me={me}
            solo={solo}
            seconds={draft.timers_enabled ? seconds : null}
            lineup={finalizing ? lineups.BLUE : null}
            editable={canEdit('BLUE')}
            menuLane={swapMenu?.side === 'BLUE' ? swapMenu.lane : null}
            onOpenMenu={(lane) => setSwapMenu(lane ? { side: 'BLUE', lane } : null)}
            onSwap={(a, b, kind) => swap('BLUE', a, b, kind)}
          />

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
                      onClick={() => {
                        if (selected !== c.id) playSound('select')
                        setSelected(c.id)
                      }}
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

          {!solo && <ChatPanel gameId={game.game_id} myUserId={game.you.user_id} />}

          <PickColumn
            side="RED"
            game={game}
            byId={byId}
            preview={preview}
            me={me}
            solo={solo}
            seconds={draft.timers_enabled ? seconds : null}
            lineup={finalizing ? lineups.RED : null}
            editable={canEdit('RED')}
            menuLane={swapMenu?.side === 'RED' ? swapMenu.lane : null}
            onOpenMenu={(lane) => setSwapMenu(lane ? { side: 'RED', lane } : null)}
            onSwap={(a, b, kind) => swap('RED', a, b, kind)}
          />
        </div>

        <footer className="cs-footer">
          <ChampionDetail champion={selectedChampion} hints={selectedChampion ? hints.get(selectedChampion.id) : undefined} />
          <div className="cs-lock">
            <ErrorNotice error={act.error ?? saveLineup.error ?? lockLineup.error} />
            {finalizing ? (
              <div className="row">
                {editableSides.map((s) => (
                  <button
                    key={s}
                    className={`cs-lock-in ${canEdit(s) ? 'mine' : ''}`}
                    disabled={!canEdit(s) || lockLineup.isPending || saveLineup.isPending}
                    onClick={() => lockLineup.mutate(s)}
                  >
                    {isReady(s)
                      ? solo ? `${sideName(s)} locked` : 'Locked in'
                      : solo ? `Lock in ${sideName(s)}` : 'Lock in lineup'}
                  </button>
                ))}
              </div>
            ) : (
              <button
                className={`cs-lock-in ${action === 'BAN' ? 'ban' : ''} ${myTurn ? 'mine' : ''}`}
                disabled={!myTurn || !selected || act.isPending}
                onClick={() => selected && act.mutate(selected)}
              >
                {action === 'BAN' ? 'Ban' : 'Lock in'}
              </button>
            )}
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
        {draft.complete ? (
          <>
            {!isSolo(game) && me === side && <span className="cs-you">you</span>}
            {(side === 'BLUE' ? game.players.blue : game.players.red)?.lineup_ready && <span className="cs-you">locked in</span>}
          </>
        ) : (
          me === side && <span className="cs-you">{isSolo(game) ? 'up now' : 'you'}</span>
        )}
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

/** Lane names as the League client writes them in champ select. */
const ROW_LANE_LABEL: Record<Lane, string> = { TOP: 'Top', JUNGLE: 'Jungle', MID: 'Mid', BOT: 'Bottom', SUPPORT: 'Support' }

/** The saved lineup of a side, if this viewer may see it (own side; both in single player; both when the game is over). */
function lineupOf(game: GameState, side: Side): Lineup | null {
  const l = game.lineup
  if (!l) return null
  const champions = isSolo(game)
    ? l[side === 'BLUE' ? 'blue' : 'red']
    : side === game.you.team ? l.yours : l.opponent
  if (!champions) return null
  return { champions: champions as Lineup['champions'], players: (l.players?.[side] ?? {}) as Lineup['players'] }
}

type RosterPlayer = Player | HiddenPlayer

function playerById(game: GameState, side: Side, id: number | undefined): RosterPlayer | null {
  const roster = game.teams[side]?.roster
  if (!roster || id === undefined) return null
  return Object.values(roster).find((p) => p?.id === id) ?? null
}

function SwapIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 2v11M2 10l3 3 3-3" />
      <path d="M11 14V3M8 6l3-3 3 3" />
    </svg>
  )
}

function InfoIcon({ size = 12 }: { size?: number }) {
  return (
    <svg className="cs-info-icon" width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" />
      <path d="M8 7.2v4M8 4.6v.2" />
    </svg>
  )
}

interface ColumnProps extends SideProps {
  solo: boolean
  seconds: number | null
  /** The side's lineup once the draft is over (null while drafting, or when it is the opponent's hidden lineup). */
  lineup: Lineup | null
  editable: boolean
  menuLane: Lane | null
  onOpenMenu: (lane: Lane | null) => void
  onSwap: (a: Lane, b: Lane, kind: SwapKind) => void
}

/**
 * One row per lane (lane icon, lane, player), like the client's team list. While drafting, picks fill
 * the rows in pick order. Afterwards the rows show the side's lineup, and its own rows get a swap menu.
 */
function PickColumn({ side, game, byId, preview, me, solo, seconds, lineup, editable, menuLane, onOpenMenu, onSwap }: ColumnProps) {
  const draft = game.draft!
  const picks = side === 'BLUE' ? draft.blue_picks : draft.red_picks
  const now = activeSlot(game, side, 'PICK')
  const roster = game.teams[side]?.roster
  const [cardLane, setCardLane] = useState<Lane | null>(null)

  const rows = LANES.map((lane, i) => {
    const player: RosterPlayer | null = (lineup ? playerById(game, side, lineup.players[lane]) : null) ?? roster?.[lane] ?? null
    const championId = lineup ? lineup.champions[lane] : picks[i]
    const locked = championId !== undefined ? byId.get(championId) : undefined
    const hovering = !locked && i === now && side === me ? preview : undefined
    const tier = lineup && locked && player && !isHidden(player) ? comfortTier((player as Player).pool, locked.id) : null
    return { lane, i, player, locked, hovering, champ: locked ?? hovering, tier }
  })

  return (
    <aside className={`cs-picks ${side.toLowerCase()}`} aria-label={`${sideName(side)} team`}>
      {rows.map(({ lane, i, player, locked, hovering, champ, tier }) => {
        const active = i === now
        const open = menuLane === lane
        const cardOpen = cardLane === lane && !!player
        return (
          <div key={lane} className="cs-row-wrap">
            <div
              className={`cs-row ${locked ? 'locked' : ''} ${hovering ? 'hovering' : ''} ${active ? 'now' : ''} ${open ? 'swapping' : ''}`}
              style={{ backgroundImage: championArt(champ) }}
            >
              <div className="cs-row-portrait">
                {champ ? <ChampionIcon champion={champ} size={60} /> : <LaneIcon lane={lane} size={30} />}
                {champ && (
                  <span className="cs-row-badge">
                    <LaneIcon lane={lane} size={12} />
                  </span>
                )}
                {editable && (
                  <button
                    className={`cs-swap-btn ${open ? 'open' : ''}`}
                    onClick={() => {
                      setCardLane(null)
                      onOpenMenu(open ? null : lane)
                    }}
                    aria-label={`Swap ${LANE_LABEL[lane]}`}
                    aria-expanded={open}
                    title="Swap champion or position"
                  >
                    <SwapIcon />
                  </button>
                )}
              </div>
              <div className="cs-row-text">
                {active && <span className="cs-row-status">{solo || side === me ? 'Picking…' : 'Opponent picking…'}</span>}
                <span className="cs-row-lane">{ROW_LANE_LABEL[lane]}</span>
                {player ? (
                  <button
                    className="cs-row-player cs-row-player-btn"
                    onClick={() => {
                      if (open) onOpenMenu(null)
                      setCardLane(cardOpen ? null : lane)
                    }}
                    aria-expanded={cardOpen}
                    title="Show player stats and champion pool"
                  >
                    <span className="cs-row-player-name">{player.name}</span>
                    <InfoIcon />
                  </button>
                ) : (
                  <span className="cs-row-player">Empty</span>
                )}
                {champ && (
                  <span className="cs-row-champ">
                    {champ.name}
                    {tier && <span className={`cs-row-tier tier-${tier.toLowerCase()}`}> · {TIER_LABEL[tier]}</span>}
                  </span>
                )}
              </div>
              {active && seconds !== null && <span className="cs-row-timer">{seconds}</span>}
            </div>
            {open && (
              <SwapMenu
                lane={lane}
                up={i >= 3}
                rows={rows.filter((r) => r.lane !== lane)}
                onSwap={(other, kind) => onSwap(lane, other, kind)}
                onClose={() => onOpenMenu(null)}
              />
            )}
            {cardOpen && player && (
              <PlayerCard player={player} up={i >= 3} game={game} byId={byId} onClose={() => setCardLane(null)} />
            )}
          </div>
        )
      })}
    </aside>
  )
}

/** Closes a row popup on Escape or a press outside its row (the row's own buttons toggle it). */
function usePopupDismiss(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.parentElement?.contains(e.target as Node)) onClose()
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])
  return ref
}

const PLAYER_STATS: { key: 'aggr' | 'aware' | 'pos' | 'dmg' | 'cs'; label: string }[] = [
  { key: 'aggr', label: 'Aggression' },
  { key: 'aware', label: 'Awareness' },
  { key: 'pos', label: 'Positioning' },
  { key: 'dmg', label: 'Damage' },
  { key: 'cs', label: 'CS' },
]

/** A player's stats and champion pool, opened from their name. Hidden opponents only show that the data is secret. */
function PlayerCard({ player, up, game, byId, onClose }: { player: RosterPlayer; up: boolean; game: GameState; byId: Map<number, Champion>; onClose: () => void }) {
  const ref = usePopupDismiss(onClose)
  const draft = game.draft!
  const banned = new Set(draft.bans.map((b) => b.champion_id))
  const picked = new Set([...draft.blue_picks, ...draft.red_picks])
  return (
    <div ref={ref} className={`cs-swap-menu cs-player-card ${up ? 'up' : ''}`} role="dialog" aria-label={`${player.name} stats and champion pool`}>
      <div className="cs-swap-head">
        <span>{player.name}</span>
        <button className="cs-swap-close" onClick={onClose} aria-label="Close">✕</button>
      </div>
      {isHidden(player) ? (
        <p className="cs-player-note">{LANE_LABEL[player.role]} · stats and champion pool stay hidden until the match ends.</p>
      ) : (
        <>
          <p className="cs-player-note">
            {[LANE_LABEL[player.role], player.region, `age ${player.age}`, player.riot?.rank && rankLabel(player.riot.rank)].filter(Boolean).join(' · ')}
          </p>
          <div className="cs-swap-group">Stats · {player.stat_total} / {player.stat_budget}</div>
          <dl className="cs-player-stats">
            {PLAYER_STATS.map((s) => (
              <div key={s.key}>
                <dt>{s.label}</dt>
                <dd>
                  <span className="cs-player-bar" aria-hidden="true"><i style={{ width: `${player[s.key] * 10}%` }} /></span>
                  {player[s.key]}
                </dd>
              </div>
            ))}
          </dl>
          <div className="cs-swap-group">Champion pool</div>
          <ol className="cs-player-pool">
            {player.pool.map((id) => {
              const tier = comfortTier(player.pool, id)
              const gone = banned.has(id) ? 'Banned' : picked.has(id) ? 'Picked' : null
              return (
                <li key={id} className={gone ? 'gone' : ''}>
                  <ChampionIcon champion={byId.get(id)} size={30} />
                  <span className="cs-player-pool-name">{byId.get(id)?.name ?? '—'}</span>
                  <span className={`cs-row-tier tier-${tier.toLowerCase()}`}>{gone ?? `${TIER_LABEL[tier]} +${TIER_MODIFIER[tier]}%`}</span>
                </li>
              )
            })}
          </ol>
        </>
      )}
    </div>
  )
}

interface SwapRow {
  lane: Lane
  player: RosterPlayer | null
  locked: Champion | undefined
}

/** "Swap for…": trade positions with a teammate (each keeps their champion) or trade champions. */
function SwapMenu({ lane, up, rows, onSwap, onClose }: { lane: Lane; up: boolean; rows: SwapRow[]; onSwap: (other: Lane, kind: SwapKind) => void; onClose: () => void }) {
  const ref = usePopupDismiss(onClose)
  return (
    <div ref={ref} className={`cs-swap-menu ${up ? 'up' : ''}`} role="dialog" aria-label={`Swap ${LANE_LABEL[lane]}`}>
      <div className="cs-swap-head">
        <span>Swap for…</span>
        <button className="cs-swap-close" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="cs-swap-group">Position</div>
      {rows.map((r) => (
        <button key={`p-${r.lane}`} className="cs-swap-option" onClick={() => onSwap(r.lane, 'position')}>
          <span className="cs-swap-icon lane"><LaneIcon lane={r.lane} size={26} /></span>
          <span className="cs-swap-text">
            <strong>{ROW_LANE_LABEL[r.lane]}</strong>
            <span>with {r.player?.name ?? 'empty lane'}</span>
          </span>
        </button>
      ))}
      <div className="cs-swap-group">Champion</div>
      {rows.map((r) => (
        <button key={`c-${r.lane}`} className="cs-swap-option" onClick={() => onSwap(r.lane, 'champion')} disabled={!r.locked}>
          <span className="cs-swap-icon"><ChampionIcon champion={r.locked} size={34} /></span>
          <span className="cs-swap-text">
            <strong>{r.locked?.name ?? '—'}</strong>
            <span>from {r.player?.name ?? ROW_LANE_LABEL[r.lane]}</span>
          </span>
        </button>
      ))}
    </div>
  )
}

function ChampionDetail({ champion: c, hints }: { champion: Champion | undefined; hints?: PoolHint[] }) {
  if (!c) return <div className="cs-detail muted">Select a champion to see its stats.</div>
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
