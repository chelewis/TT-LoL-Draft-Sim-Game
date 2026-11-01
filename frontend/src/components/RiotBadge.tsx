import type { Player } from '../api/types'
import { importCheckBadge } from '../lib/format'

/** "Riot ✓" (genuine, unedited import), "Riot · edited" or "Riot · unverified", with the details on hover. */
export default function RiotBadge({ riot, showAccount = false }: { riot: Player['riot']; showAccount?: boolean }) {
  if (!riot) return null
  const badge = importCheckBadge(riot.import_check)
  const account = `${riot.game_name}#${riot.tag_line}`
  const cls = badge.tone === 'ok' ? 'badge ok' : badge.tone === 'warn' ? 'badge badge-warn' : 'badge'
  return (
    <span className={cls} title={`${badge.title}. Account: ${account} (ownership unverified)`}>
      {badge.text}{showAccount ? ` ${account}` : ''}
    </span>
  )
}
