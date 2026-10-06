export type Side = 'BLUE' | 'RED'
export type Lane = 'TOP' | 'JUNGLE' | 'MID' | 'BOT' | 'SUPPORT'
export const LANES: Lane[] = ['TOP', 'JUNGLE', 'MID', 'BOT', 'SUPPORT']
export const STYLES = ['early', 'scaling', 'teamfight', 'skirmish'] as const

export interface User {
  id: number
  username: string
  email: string
}

export interface Champion {
  id: number
  name: string
  class: string
  difficulty: number
  damage_type: string
  damage: number
  sturdiness: number
  crowd_control: number
  mobility: number
  utility: number
  win_rate: number
  pick_rate: number
  strength: string
  weakness: string
}

export interface Player {
  id: number
  name: string
  role: Lane
  age: number
  region: string
  aggr: number
  aware: number
  pos: number
  dmg: number
  cs: number
  pool: number[]
  stat_total: number
  stat_budget: number             // this player's soft stat ceiling (higher for high-rank Riot imports)
  over_budget_by: number
  is_default: boolean
  riot?: {
    game_name: string
    tag_line: string
    region: string
    imported_at: string | null
    verified: boolean
    data_source?: string | null   // SOLO | FLEX | NORMAL: which queue the stats came from
    games_used?: number | null
    is_solo_source?: boolean
    rank?: RiotRank | null        // rank at import time; null when unranked or imported before ranks were read
  } | null
}

/** A ranked standing from Riot. Master and above have no division. */
export interface RiotRank {
  queue: string | null            // SOLO | FLEX: which queue the rank is from
  tier: string | null             // e.g. EMERALD; null when unranked
  division: string | null
  lp: number | null
  wins: number | null
  losses: number | null
}

/** One real-world measurement behind a stat: the player's average, the role benchmark and the 1-10 score it earned. */
export interface RiotMetric {
  metric: string
  label: string
  unit: 'percent' | 'number'
  how: string
  value: number
  low: number
  high: number
  lower_is_better: boolean
  score: number
}

export interface RiotPreview {
  player: { name: string; role: Lane; age: number; region: string; aggr: number; aware: number; pos: number; dmg: number; cs: number; pool: number[] }
  riot: { game_name: string; tag_line: string; region: string }
  riot_ref: string
  analysis: {
    games: number
    raw_stats: Record<string, number>
    rank: RiotRank & { budget: number; floor: number }   // the stat ceiling and floor for this rank (floor 0: none)
    fitted_to_budget: boolean
    raised_to_floor: boolean
    missing_pool_slots: number
    notes: string[]
    source: { queue: string; label: string; games: number; is_solo: boolean; tried: Record<string, number> }
    breakdown: Record<string, RiotMetric[]>
    fit: { budget: number; floor: number; total_before: number; total_after: number }
  }
}

/** A player as shown to the opponent when `hide_player_data` is on. */
export interface HiddenPlayer {
  id: number
  name: string
  role: Lane
  hidden: true
  over_budget_by?: number
  is_default?: boolean
}

export interface Coach {
  id: number
  name: string
  draft: number
  synergy: number
  is_default: boolean
}

export interface OverBudgetPlayer {
  player_id: number
  name: string
  over_by: number
  total?: number
}

export interface Team {
  id: number
  name: string
  logo: string
  region: string
  fanbase: string
  style1: string | null
  style2: string | null
  focus1: string | null
  focus2: string | null
  coach: Coach | null
  roster: Record<Lane, Player | HiddenPlayer | null>
  selectable?: boolean
  issues?: string[]
  over_budget: boolean
  over_budget_players: OverBudgetPlayer[]
  is_default?: boolean
  hidden?: boolean
}

export interface LobbySettings {
  mode: 'SOLO' | 'MULTI'   // SOLO: one person plays both sides
  hide_player_data: boolean
  bans_enabled: boolean
  timers_enabled: boolean
  pick_seconds: number
  ban_seconds: number
}

export interface DraftView {
  actions: string[]
  timers_enabled: boolean
  pick_seconds: number
  ban_seconds: number
  current_action: number
  current_team: Side | null
  action_type: 'PICK' | 'BAN' | null
  started_at: string | null
  expires_at: string | null
  bans: { team: Side; champion_id: number }[]
  blue_picks: number[]
  red_picks: number[]
  history: { action_number: number; team: Side; action_type: string; champion_id: number; auto: boolean }[]
  complete: boolean
}

export interface GameUser {
  id: number
  username: string
  team_id: number | null
  ready: boolean
  lineup_ready: boolean
}

export type GameStatus =
  | 'WAITING_FOR_PLAYERS'
  | 'TEAM_SELECTION'
  | 'READY_CHECK'
  | 'DRAFTING'
  | 'LANE_ASSIGNMENT'
  | 'READY_TO_SIMULATE'
  | 'SIMULATING'
  | 'COMPLETED'
  | 'CANCELLED'

export interface GameState {
  game_id: number
  lobby_id: number
  lobby_code: string
  status: GameStatus
  settings: LobbySettings
  expires_at: string | null
  you: { user_id: number; team: Side; is_owner: boolean }
  players: { blue: GameUser | null; red: GameUser | null }
  teams: { BLUE: Team | null; RED: Team | null }
  draft: DraftView | null
  lineup: {
    yours: Record<string, number>
    opponent?: Record<string, number>
    blue?: Record<string, number>
    red?: Record<string, number>
    /** lane -> player id for each side this viewer may see (a position swap moves players off their roster lane) */
    players?: Partial<Record<Side, Record<string, number>>>
  } | null
  result_available: boolean
}

export interface LobbySummary {
  id: number
  code: string
  game_id: number
  status: GameStatus
  settings: LobbySettings
  expires_at: string
  you: Side | null
}

export interface ResultPlayer {
  player_id: number
  name: string
  team: Side
  lane: Lane
  champion_id: number
  champion: string
  comfort_tier: string
  lane_score: number
  kills: number
  deaths: number
  assists: number
  cs: number
  gold: number
  kda: number
  rank: number
  rank_score: number
}

export interface ResultTeam {
  name: string
  gold: number
  kills: number
  towers: number
  inhibitors: number
  dragons: number
  barons: number
  soul: boolean
  comp: { win_rate: number; damage_profile: { physical: number; magic: number } }
}

export interface ResultLane {
  blue_player: number
  red_player: number
  blue_champion: number
  red_champion: number
  blue_score: number
  red_score: number
  gold_diff: number
  winner: Side | null
  matchup: string | null
}

export interface MatchResult {
  game_id: number
  winner: Side
  win_condition: 'NEXUS' | 'TIMEOUT'
  duration_seconds: number
  simulation_version: string
  seed: number
  mvp: { player_id: number; name: string; champion: string; team: Side }
  ace: { player_id: number; name: string; champion: string; team: Side }
  teams: Record<Side, ResultTeam>
  lanes: Record<Lane, ResultLane>
  players: ResultPlayer[]
  draft: {
    bans: { team: Side; champion_id: number }[]
    blue_picks: number[]
    red_picks: number[]
  }
  teams_info: Record<Side, Team>
}

export interface MatchEvent {
  sequence: number
  phase: string
  minute: number
  type: string
  payload: Record<string, unknown>
}

export interface ComfortPreview {
  lane: Lane
  player_id: number
  champion_id: number
  tier: string
  modifier: number
}

/** One line of a game's all-chat. */
export interface ChatMessage {
  id: number
  user_id: number
  username: string
  team: Side
  body: string
  created_at: string
}
