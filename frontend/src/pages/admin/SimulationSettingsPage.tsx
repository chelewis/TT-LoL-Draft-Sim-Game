import ComingSoon from './ComingSoon'

export default function SimulationSettingsPage() {
  return (
    <ComingSoon
      title="Simulation Settings"
      summary="The numbers that decide how a match plays out once the draft is done."
      items={[
        'Comfort modifiers by champion pool position',
        'Lane phase: roll range, score scale, matchup multipliers and assists',
        'Economy: gold per CS, kills, assists, towers and bounties',
        'Game phases and overtime: minutes, fights and objective limits',
        'Objectives: dragons, soul, elder and baron',
        'Structures and sieges',
        'Fights: damage, sturdiness and control weights',
        'Team style bonuses and coach effects',
      ]}
    />
  )
}
