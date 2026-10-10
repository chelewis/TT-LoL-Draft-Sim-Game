import ComingSoon from './ComingSoon'

export default function GlobalsPage() {
  return (
    <ComingSoon
      title="Globals"
      summary="Rules that apply outside the match simulation: lobbies, the draft, and what players may build."
      items={[
        'Draft timer and lobby expiry',
        'Player and coach stat budgets',
        'Stat ceilings and floors by Riot rank',
        'Stat range and champion pool size',
        'Limits on teams, players and coaches per user',
      ]}
    />
  )
}
