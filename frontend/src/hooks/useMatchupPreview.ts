import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { GameState, MatchupPreview } from '../api/types'

/** GET /games/{id}/matchups once the draft is done. The pick columns and the "Show Matchup Data" panel share it.
 * My own swaps change the key. The opponent's swaps arrive as LINEUP_UPDATED, which GamePage turns into a refetch. */
export function useMatchupPreview(game: GameState, enabled = true) {
  return useQuery({
    queryKey: ['matchups', game.game_id, game.lineup],
    queryFn: () => api<MatchupPreview>(`/games/${game.game_id}/matchups`),
    placeholderData: keepPreviousData,
    enabled,
  })
}
