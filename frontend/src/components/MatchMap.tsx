import { useState } from 'react'
import type { Champion, MatchEvent, MatchResult, ResultPlayer, Side } from '../api/types'
import { useDDragonVersion } from '../hooks/useData'
import { minimapUrl } from '../lib/ddragon'
import { LANE_LABEL, TIER_LABEL } from '../lib/format'
import {
  BARON_PIT, DRAGON_PIT, MAP_LAYOUT, STRUCTURE_LANES, buildMapState,
  type MapState, type Point, type SideMapState,
} from '../lib/mapState'
import { ChampionIcon } from './ChampionArt'

const SIDES: Side[] = ['BLUE', 'RED']
const other = (s: Side): Side => (s === 'BLUE' ? 'RED' : 'BLUE')
const at = (p: Point) => ({ left: `${p.x}%`, top: `${p.y}%` })

/** A destroyed structure keeps its outline and gains a cross, so the state never depends on colour alone. */
function Cross({ p, r }: { p: Point; r: number }) {
  return (
    <g className="map-cross">
      <line x1={p.x - r} y1={p.y - r} x2={p.x + r} y2={p.y + r} />
      <line x1={p.x - r} y1={p.y + r} x2={p.x + r} y2={p.y - r} />
    </g>
  )
}

function Tower({ p, down }: { p: Point; down: boolean }) {
  return (
    <g className={down ? 'map-structure down' : 'map-structure'}>
      <rect x={p.x - 1.5} y={p.y - 1.5} width={3} height={3} rx={0.4} />
      {down && <Cross p={p} r={1.5} />}
    </g>
  )
}

function Inhibitor({ p, down }: { p: Point; down: boolean }) {
  return (
    <g className={down ? 'map-structure down' : 'map-structure'}>
      <circle cx={p.x} cy={p.y} r={1.9} />
      {!down && <circle className="map-structure-core" cx={p.x} cy={p.y} r={0.8} />}
      {down && <Cross p={p} r={1.4} />}
    </g>
  )
}

function Nexus({ p, down }: { p: Point; down: boolean }) {
  return (
    <g className={down ? 'map-structure map-nexus down' : 'map-structure map-nexus'}>
      {down && <circle className="map-nexus-blast" cx={p.x} cy={p.y} r={7.5} />}
      <circle cx={p.x} cy={p.y} r={4} />
      {!down && <circle className="map-structure-core" cx={p.x} cy={p.y} r={1.8} />}
      {down && <Cross p={p} r={3.4} />}
    </g>
  )
}

function Structures({ side, state }: { side: Side; state: SideMapState }) {
  const layout = MAP_LAYOUT[side]
  return (
    <g className={`map-side-${side.toLowerCase()}`}>
      {STRUCTURE_LANES.map((lane) => (
        <g key={lane}>
          {layout.towers[lane].map((p, i) => <Tower key={i} p={p} down={i < state.towersLost[lane]} />)}
          <Inhibitor p={layout.inhibitors[lane]} down={state.inhibitorsLost[lane]} />
        </g>
      ))}
      {layout.nexusTowers.map((p, i) => <Tower key={i} p={p} down={i < state.nexusTowersLost} />)}
      <Nexus p={layout.nexus} down={state.nexusDestroyed} />
    </g>
  )
}

/** The Summoner's Rift minimap; the plain ground shows through if Data Dragon can't supply it. */
function Terrain() {
  const version = useDDragonVersion()
  const [failed, setFailed] = useState(false)
  return (
    <g>
      <rect className="map-ground" x={0} y={0} width={100} height={100} />
      {version && !failed && (
        <image className="map-image" href={minimapUrl(version)} x={0} y={0} width={100} height={100}
          preserveAspectRatio="none" onError={() => setFailed(true)} />
      )}
      <rect className="map-shade" x={0} y={0} width={100} height={100} />
      {/* the losing base burns: shown through CSS when its nexus fell */}
      <circle className="map-base-ruin map-base-ruin-blue" cx={MAP_LAYOUT.BLUE.nexus.x} cy={MAP_LAYOUT.BLUE.nexus.y} r={19} />
      <circle className="map-base-ruin map-base-ruin-red" cx={MAP_LAYOUT.RED.nexus.x} cy={MAP_LAYOUT.RED.nexus.y} r={19} />
    </g>
  )
}

function PlayerMarker({ player, champion, teamName, mvp, ace }: {
  player: ResultPlayer; champion: Champion | undefined; teamName: string; mvp: boolean; ace: boolean
}) {
  const honours = [mvp && 'MVP', ace && 'ACE'].filter(Boolean).join(' and ')
  const label = `${player.name}, ${player.champion}, ${LANE_LABEL[player.lane]}: performance score ${player.rank_score.toLocaleString()}, `
    + `ranked ${player.rank} of 10, ${player.kills}/${player.deaths}/${player.assists}, ${player.cs} CS, ${player.gold.toLocaleString()} gold`
    + (honours ? `, ${honours}` : '')
  const slot = MAP_LAYOUT[player.team].champions[player.lane]
  // the detail card opens towards the middle of the map so it never hangs off an edge
  const card = `map-card ${slot.y < 50 ? 'below' : 'above'} ${slot.x < 30 ? 'from-left' : slot.x > 70 ? 'from-right' : ''}`
  return (
    <div className={`map-champ map-champ-${player.team.toLowerCase()} ${honours ? 'map-champ-honoured' : ''}`} style={at(slot)}
      tabIndex={0} role="img" aria-label={label}>
      <ChampionIcon champion={champion} size={40} />
      <span className="map-score">{player.rank_score.toLocaleString()}</span>
      <div className={card} aria-hidden="true">
        <strong>{player.name}</strong>
        <span className="muted">{player.champion} · {LANE_LABEL[player.lane]} · {teamName}</span>
        {honours && <span className="map-card-honour">{mvp && 'MVP: best player on the winning team'}{mvp && ace && <br />}{ace && 'ACE: best player in the game'}</span>}
        <dl>
          <dt>Performance score</dt><dd>{player.rank_score.toLocaleString()} (#{player.rank} of 10)</dd>
          <dt>K / D / A</dt><dd>{player.kills} / {player.deaths} / {player.assists} (KDA {player.kda})</dd>
          <dt>CS</dt><dd>{player.cs}</dd>
          <dt>Gold</dt><dd>{player.gold.toLocaleString()}</dd>
          {player.damage_dealt != null && <><dt>Damage dealt</dt><dd>{player.damage_dealt.toLocaleString()}</dd></>}
          {player.damage_taken != null && <><dt>Damage taken</dt><dd>{player.damage_taken.toLocaleString()}</dd></>}
          <dt>Champion pool</dt><dd>{TIER_LABEL[player.comfort_tier] ?? player.comfort_tier}</dd>
        </dl>
      </div>
    </div>
  )
}

function Objective({ p, name, state, extra }: { p: Point; name: string; state: MapState; extra?: (s: SideMapState) => string }) {
  const count = (s: SideMapState) => (name === 'Baron' ? s.barons : s.dragons)
  const label = SIDES.map((side) => `${side === 'BLUE' ? 'Blue' : 'Red'} ${count(state[side])}${extra ? extra(state[side]) : ''}`).join(', ')
  return (
    <div className="map-objective" style={at(p)} title={`${name}s taken: ${label}`} role="img" aria-label={`${name}s taken: ${label}`}>
      <span className="map-objective-name">{name}</span>
      <span className="map-objective-counts">
        <b className="map-count-blue">{count(state.BLUE)}</b>
        <span>:</span>
        <b className="map-count-red">{count(state.RED)}</b>
      </span>
    </div>
  )
}

/**
 * The map as it stood when the game ended: champions by role with their scores, structures, objectives and nexuses.
 * With `live` it is the map mid-game for the events so far: nothing that gives the outcome away (scores, MVP and
 * ACE, the verdict) is shown.
 */
export default function MatchMap({ result, events, champions, names, live = false }: {
  result: MatchResult; events: MatchEvent[]; champions: Map<number, Champion>; names: Record<Side, string>; live?: boolean
}) {
  const state = buildMapState(events)
  const fallen = SIDES.find((side) => state[side].nexusDestroyed)
  const dragonExtra = (s: SideMapState) => `${s.soul ? ' with the soul' : ''}${s.elder ? ' and the Elder Dragon' : ''}`
  const markers = SIDES.flatMap((side) => [state[side].soul && `${names[side]} hold the dragon soul`, state[side].elder && `${names[side]} took the Elder Dragon`])
    .filter(Boolean)

  return (
    <figure className="match-map-figure">
      <div className={`match-map ${fallen ? `nexus-fell-${fallen.toLowerCase()}` : ''}`}>
        <svg viewBox="0 0 100 100" aria-hidden="true">
          <Terrain />
          {SIDES.map((side) => <Structures key={side} side={side} state={state[side]} />)}
        </svg>
        {fallen && (
          <div className="map-nexus-spot" style={at(MAP_LAYOUT[fallen].nexus)} tabIndex={0} role="img" aria-label={`${names[fallen]}'s nexus: destroyed`}>
            <span className={`map-nexus-label ${fallen === 'BLUE' ? 'above' : 'below'}`} aria-hidden="true">Nexus destroyed</span>
          </div>
        )}
        <Objective p={BARON_PIT} name="Baron" state={state} />
        <Objective p={DRAGON_PIT} name="Dragon" state={state} extra={dragonExtra} />
        {result.players.map((p) => live ? (
          <div key={`${p.team}:${p.lane}`} className={`map-champ map-champ-${p.team.toLowerCase()}`} style={at(MAP_LAYOUT[p.team].champions[p.lane])}
            role="img" aria-label={`${p.name}, ${p.champion}, ${LANE_LABEL[p.lane]}, ${names[p.team]}`}>
            <ChampionIcon champion={champions.get(p.champion_id)} size={40} />
          </div>
        ) : (
          <PlayerMarker key={p.player_id} player={p} champion={champions.get(p.champion_id)} teamName={names[p.team]}
            mvp={p.player_id === result.mvp.player_id} ace={p.player_id === result.ace.player_id} />
        ))}
      </div>
      {!live && <figcaption className="stack">
        <p>
          {fallen
            ? <><strong>{names[other(fallen)]}</strong> destroyed <strong>{names[fallen]}</strong>'s nexus.</>
            : <>No nexus fell: <strong>{names[result.winner]}</strong> won on time.</>}
          {markers.length > 0 && ` ${markers.join('. ')}.`}
        </p>
        <ul className="map-legend small muted">
          <li><span className="map-key map-key-blue" /> {names.BLUE}</li>
          <li><span className="map-key map-key-red" /> {names.RED}</li>
          <li><svg viewBox="0 0 6 6" aria-hidden="true"><rect className="map-key-shape" x={1} y={1} width={4} height={4} rx={0.5} /></svg> tower</li>
          <li><svg viewBox="0 0 6 6" aria-hidden="true"><circle className="map-key-shape" cx={3} cy={3} r={2.2} /></svg> inhibitor or nexus</li>
          <li><svg viewBox="0 0 6 6" aria-hidden="true"><rect className="map-key-shape down" x={1} y={1} width={4} height={4} rx={0.5} /><path className="map-key-cross" d="M1 1l4 4M1 5l4-4" /></svg> destroyed</li>
          <li><span className="map-key map-key-gold" /> MVP or ACE</li>
          <li>Number under a champion: performance score (hover for details)</li>
          <li>Dragon and Baron: taken by blue : red</li>
        </ul>
      </figcaption>}
    </figure>
  )
}
