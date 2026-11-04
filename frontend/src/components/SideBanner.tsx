import type { GameState } from '../api/types'
import { isCpu, isSolo, seriesShort } from '../lib/format'

/** "Game 2 · Bo3 (1–0)" for a game in a series, from this game's Blue side first. `hideResult` leaves this
 * game's win out of the score, so the banner doesn't give the result away while the replay plays. */
function seriesTag(game: GameState, hideResult: boolean): string | null {
  const s = game.series
  if (!s) return null
  const score = { ...s.score }
  if (hideResult && s.loser_side) score[s.loser_side === 'BLUE' ? 'RED' : 'BLUE'] -= 1
  return `Game ${s.game_number} · ${seriesShort(s.format)}${s.fearless ? ' Fearless' : ''} (${score.BLUE}–${score.RED})`
}

/** Brightly coloured bar that always tells the player which side they are on. */
export default function SideBanner({ game, hideResult = false }: { game: GameState; hideResult?: boolean }) {
  const tag = seriesTag(game, hideResult)
  if (isSolo(game)) {
    const turn = game.status === 'DRAFTING' ? game.draft?.current_team : null
    return (
      <div className={`side-banner solo ${turn ? turn.toLowerCase() : ''}`} role="status">
        <span>Single player: you control both sides</span>
        {turn && <span className="sub">· {turn === 'BLUE' ? 'Blue' : 'Red'} to {game.draft?.action_type === 'PICK' ? 'pick' : 'ban'}</span>}
        {tag && <span className="sub">· {tag}</span>}
      </div>
    )
  }
  const side = game.you.team
  const name = game.teams[side]?.name
  const label = side === 'BLUE' ? 'Blue' : 'Red'
  return (
    <div className={`side-banner ${side.toLowerCase()}`} role="status" aria-label={`You are playing on the ${label} side`}>
      <span>You are playing {label} side</span>
      {name && <span className="sub">· {name}</span>}
      {isCpu(game) ? <span className="sub">· vs CPU</span> : game.you.is_owner && <span className="sub">· lobby owner</span>}
      {tag && <span className="sub">· {tag}</span>}
    </div>
  )
}
