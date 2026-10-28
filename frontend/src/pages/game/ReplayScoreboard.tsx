import type { ReactNode } from 'react'
import type { Champion, Lane, MatchResult, Side } from '../../api/types'
import { LANES } from '../../api/types'
import { ChampionIcon, LaneIcon } from '../../components/ChampionArt'
import { formatDuration } from '../../lib/format'
import { formatGold, formatThousands, goldDiff, playerKey, type Score, type TeamScore } from '../../lib/scoreboard'

const ICONS: Record<'tower' | 'gold' | 'kills', ReactNode> = {
  tower: <path d="M7 3h2v2h2V3h2v2h2V3h2v5l-2 2v8h2v3H7v-3h2v-8L7 8z" />,
  gold: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5.5" fill="none" stroke="#1a1400" strokeWidth="1.5" /></>,
  kills: <path d="M4 3l9 9-2 2-9-9V3zM20 3l-9 9 2 2 9-9V3zM5 16l3 3-3 2-2-2zM19 16l-3 3 3 2 2-2z" />,
}

function Icon({ name }: { name: keyof typeof ICONS }) {
  return <svg className={`replay-icon replay-icon-${name}`} width={16} height={16} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">{ICONS[name]}</svg>
}

function TeamPanel({ side, name, team }: { side: Side; name: string; team: TeamScore }) {
  return (
    <div className={`replay-hud-team ${side.toLowerCase()}`}>
      <span className="replay-team">{name}</span>
      <div className="replay-stats">
        <span className="replay-stat" role="img" aria-label={`Towers destroyed: ${team.towers}`} title="Towers destroyed">
          <Icon name="tower" />{team.towers}
        </span>
        {team.gold != null && (
          <span className="replay-stat" role="img" aria-label={`Gold: ${team.gold.toLocaleString()}`} title="Team gold">
            <Icon name="gold" />{formatGold(team.gold)}
          </span>
        )}
      </div>
      <div className="replay-objectives small muted">
        <span>Dragons {team.dragons}</span>
        <span>Barons {team.barons}</span>
        <span>Inhibitors {team.inhibitors}</span>
        {team.soul && <span className="badge gold">Soul</span>}
        {team.elder && <span className="badge gold">Elder</span>}
      </div>
    </div>
  )
}

/** The gold difference, with an arrow pointing at the side that leads, in that side's colour. */
function GoldLead({ names, diff }: { names: Record<Side, string>; diff: number | null }) {
  if (diff == null) return null
  const leader: Side | null = diff > 0 ? 'BLUE' : diff < 0 ? 'RED' : null
  const arrow = (points: string) => (
    <svg className="replay-gold-arrow" width={12} height={12} viewBox="0 0 12 12" fill="currentColor" aria-hidden="true"><path d={points} /></svg>
  )
  return (
    <span
      className={`replay-gold-diff ${leader ? leader.toLowerCase() : 'even'}`}
      role="img"
      aria-label={leader ? `Gold lead: ${names[leader]} by ${Math.abs(diff).toLocaleString()}` : 'Gold even'}
      title="Gold difference"
    >
      {leader === 'BLUE' && arrow('M9 1L2 6l7 5z')}
      {formatGold(Math.abs(diff))}
      {leader === 'RED' && arrow('M3 1l7 5-7 5z')}
    </span>
  )
}

/** Broadcast-style top bar: each side's towers, gold and objectives around the kill score and the game clock. */
export function ReplayHud({ names, score, clockSeconds }: { names: Record<Side, string>; score: Score; clockSeconds: number }) {
  return (
    <div className="replay-hud">
      <TeamPanel side="BLUE" name={names.BLUE} team={score.teams.BLUE} />
      <div className="replay-hud-centre">
        <div className="replay-kills" role="img" aria-label={`Kills: ${names.BLUE} ${score.teams.BLUE.kills}, ${names.RED} ${score.teams.RED.kills}`}>
          <b className="blue">{score.teams.BLUE.kills}</b>
          <Icon name="kills" />
          <b className="red">{score.teams.RED.kills}</b>
        </div>
        <span className="replay-clock" role="timer" aria-label="Game time">{formatDuration(clockSeconds)}</span>
        <GoldLead names={names} diff={goldDiff(score)} />
      </div>
      <TeamPanel side="RED" name={names.RED} team={score.teams.RED} />
    </div>
  )
}

/** Both teams' players lane by lane, blue on the left and red mirrored on the right. */
export function ReplayPlayers({ result, score, champions }: { result: MatchResult; score: Score; champions: Map<number, Champion> }) {
  const showGold = score.teams.BLUE.gold != null
  const showDamage = Object.values(score.players).some((s) => s.damageDealt != null)
  const columns = 3 + (showGold ? 1 : 0) + (showDamage ? 1 : 0)
  const cells = (side: Side, lane: Lane) => {
    const p = result.players.find((x) => x.team === side && x.lane === lane)
    const s = score.players[playerKey(side, lane)]
    if (!p || !s) return Array.from({ length: columns }, (_, i) => <td key={`${side}${i}`} />)
    const out = [
      <td key={`${side}p`} className={`replay-player ${side.toLowerCase()}`}>
        <span className="replay-player-tag">
          <ChampionIcon champion={champions.get(p.champion_id)} size={28} />
          <span className="replay-player-name">{p.name}<span className="muted small"> {p.champion}</span></span>
        </span>
      </td>,
      showGold && <td key={`${side}g`} className="num replay-gold">{(s.gold ?? 0).toLocaleString()}</td>,
      <td key={`${side}k`} className="num">{s.kills}/{s.deaths}/{s.assists}</td>,
      <td key={`${side}c`} className="num">{s.cs}</td>,
      showDamage && (
        <td key={`${side}d`} className="num" title="Damage dealt / taken">
          {formatThousands(s.damageDealt ?? 0)} / {formatThousands(s.damageTaken ?? 0)}
        </td>
      ),
    ]
    return side === 'BLUE' ? out : out.reverse()
  }
  const heads = (side: Side) => {
    const out = [<th key={`${side}p`} className={`replay-player ${side.toLowerCase()}`}>Player</th>, showGold && <th key={`${side}g`} className="num">Gold</th>,
      <th key={`${side}k`} className="num">K/D/A</th>, <th key={`${side}c`} className="num">CS</th>,
      showDamage && <th key={`${side}d`} className="num" title="Damage dealt / taken">Dmg</th>]
    return side === 'BLUE' ? out : out.reverse()
  }
  return (
    <div className="table-scroll">
      <table className="compact replay-players">
        <thead>
          <tr>{heads('BLUE')}<th aria-label="Lane" />{heads('RED')}</tr>
        </thead>
        <tbody>
          {LANES.map((lane) => (
            <tr key={lane}>
              {cells('BLUE', lane)}
              <td className="replay-lane"><LaneIcon lane={lane} size={18} /></td>
              {cells('RED', lane)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
