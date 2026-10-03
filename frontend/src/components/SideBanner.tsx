import type { GameState } from '../api/types'
import { isSolo } from '../lib/format'

/** Brightly coloured bar that always tells the player which side they are on. */
export default function SideBanner({ game }: { game: GameState }) {
  if (isSolo(game)) {
    const turn = game.status === 'DRAFTING' ? game.draft?.current_team : null
    return (
      <div className={`side-banner solo ${turn ? turn.toLowerCase() : ''}`} role="status">
        <span>Single player: you control both sides</span>
        {turn && <span className="sub">· {turn === 'BLUE' ? 'Blue' : 'Red'} to {game.draft?.action_type === 'PICK' ? 'pick' : 'ban'}</span>}
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
      {game.you.is_owner && <span className="sub">· lobby owner</span>}
    </div>
  )
}
