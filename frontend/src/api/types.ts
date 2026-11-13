export type Side = 'BLUE' | 'RED'
export type Lane = 'TOP' | 'JUNGLE' | 'MID' | 'BOT' | 'SUPPORT'
export const LANES: Lane[] = ['TOP', 'JUNGLE', 'MID', 'BOT', 'SUPPORT']
export const STYLES = ['early', 'scaling', 'teamfight', 'skirmish'] as const

export interface User {
  id: number
  username: string
  email: string
  is_admin: boolean
}

/** Admin win rate matrices: champions on the same team ('ally') or on opposite teams ('enemy'). */
export type MatchupKind = 'ally' | 'enemy'
export interface MatchupChampion {
  id: number
  name: string
}
/** [champion a, champion b, win rate % or null, games, edited]; a < b, and for 'enemy' the rate is champion a's. */
export type MatchupCell = [number, number, number | null, number, boolean]
export interface MatchupMatrix {
  kind: MatchupKind
  champions: MatchupChampion[]
  cells: MatchupCell[]
}

/** One admin-editable simulation constant (backend EDITABLE_SETTINGS). `path` is its dotted config key. */
export type SimulationSettingField = {
  path: string
  group: string
  label: string
  help: string
  default: number | boolean
  value: number | boolean
} & ({ kind: 'bool' } | { kind: 'number'; min: number; max: number; step: number })
/** Champion columns admins can edit on Admin → Champions → Info (backend champion_admin_service.EDITABLE). */
export type AdminChampionColumn =
  | 'win_rate' | 'pick_rate' | 'style' | 'difficulty' | 'damage_type' | 'damage' | 'sturdiness'
  | 'crowd_control' | 'mobility' | 'utility' | 'scaling' | 'attack_range' | 'waveclear'

export interface AdminChampionField {
  kind: 'int' | 'float' | 'choice'
  min: number
  max: number
  choices: string[]
}

/** One row of GET /admin/champions. */
export type AdminChampion = {
  id: number
  name: string
  class: string
  enabled: boolean
  roles: Lane[]
  /** columns an admin has changed; the startup CSV sync leaves them alone until reset */
  edited: AdminChampionColumn[]
  /** the CSV value of each edited column (what a reset brings back) */
  seed: Partial<Record<AdminChampionColumn, number | string>>
  in_seed: boolean
  updated_at: string | null
} & Record<AdminChampionColumn, number | string>

export interface AdminChampions {
  fields: Record<AdminChampionColumn, AdminChampionField>
  champions: AdminChampion[]
}

/** GET /admin/users: one row per site user. */
export interface AdminUser {
  id: number
  username: string
  email: string
  is_admin: boolean
  created_at: string | null
  /** when an admin last reset the password; null if never */
  password_changed_at: string | null
  teams: number
  players: number
  /** finished games played */
  games: number
}

export interface SimulationSettings {
  fields: SimulationSettingField[]
  updated_at: string | null
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
  /** 1 early game, 2 neutral, 3 late game */
  scaling: number
  /** 1 melee, 2 short range, 3 long range */
  range: number
  /** 1 weak, 2 average, 3 strong */
  waveclear: number
  /** usual lanes, most played first; empty = no role data (never off-role) */
  roles: Lane[]
  strength: string
  weakness: string
}

/** One row of GET /meta/champions: how a champion is doing in the game's meta. */
export interface MetaChampion {
  id: number
  name: string
  class: string
  roles: Lane[]
  /** main role (first of roles); win_rate only counts opponents with the same main role */
  role: Lane | null
  /** percent; expected win rate against a lane opponent from the against-team win rate table, or the champion's own rate */
  win_rate: number
  win_rate_source: 'matchups' | 'base'
  /** same-lane opponents with data in the against-team table */
  opponents: number
  /** percent */
  pick_rate: number
}

/** A champion as GET /meta/pair describes it. */
export interface PairChampion {
  id: number
  name: string
  class: string
  roles: Lane[]
  /** "P", "M" or "PM" */
  damage_type: string
  /** 1 melee, 2 short range, 3 long range */
  range: number
  /** 1 early game, 2 neutral, 3 late game */
  scaling: number
  /** 1 weak, 2 average, 3 strong */
  waveclear: number
  /** matchup wheel type */
  strength: string
  weakness: string
}

/** A note on how two champions interact in the simulation. Same team: strength / weakness / neutral. Against
 * team: which champion the effect favours (a = the first, b = the second), or even. */
export interface PairNote {
  kind: 'strength' | 'weakness' | 'neutral' | 'a' | 'b' | 'even'
  title: string
  detail: string
  weight: number
}

/** Where a pair's win rate came from: games behind it, and whether an admin set it. */
export interface PairRate {
  /** percent, or null when the table has no value */
  win_rate: number | null
  games: number
  edited: boolean
  notes: PairNote[]
}

/** GET /meta/pair?a=&b=: how two champions do together and against each other. */
export interface ChampionPair {
  champions: [PairChampion, PairChampion]
  same_team: PairRate
  /** win_rate is the first champion's against the second */
  against: PairRate & {
    /** the lane where they would face each other; null when they never share one */
    lane: Lane | null
    /** same role (true), or across the bot lane, bot vs support (false) */
    head_to_head: boolean
  }
}

/** One row of POST /champion-fit: lane fit of a champion for given stats and pool, best first. */
export interface ChampionFit {
  champion_id: number
  name: string
  class: string
  score: number
  base: number
  comfort_tier: string
  top_stat: 'aggr' | 'aware' | 'pos' | 'dmg'
  strength: 'Offence' | 'Defence' | 'Control'
  /** Lane multiplier from the stats behind the champion's strength (0.75 to 1.25). */
  strength_fit: number
  /** Which of the player's lanes suits the champion best; null when no role was given. */
  lane: Lane | null
  role_status: RoleStatus
  /** Fraction of the score the off-role rule takes (0 when none). Penalised champions are listed last. */
  off_role_penalty: number
}

export interface Player {
  id: number
  name: string
  role: Lane
  secondary_role: Lane | null   // optional second lane the player can be rostered in
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
  /** shared publicly (others can find and copy it) */
  is_public?: boolean
  /** why the owner can't make it public (empty when they can) */
  share_issues?: string[]
  tags?: PlaystyleTag[]           // playstyle tags in effect (only on Riot imports)
  earned_tags?: PlaystyleTag[]    // every tag the Riot import earned, to choose from in the editor
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
    import_check?: ImportCheck     // genuine import? edited since? (missing on games started before seals)
  } | null
}

/** Whether a Riot player is a genuine import and what was changed since (server-signed baseline). */
export interface ImportCheck {
  status: 'none' | 'unedited' | 'edited' | 'unverified'
  edited_fields: string[]          // role, aggr, aware, pos, dmg, cs, pool, tags
  original: { role: Lane; aggr: number; aware: number; pos: number; dmg: number; cs: number; pool: number[]; negative_tags: string[] } | null
}

/** One effect of a playstyle tag on the simulation; hooks are listed in lib/playstyle.ts. */
export interface PlaystyleEffect {
  hook: string
  value: number
}

/** Why a Riot account earned a tag: a challenge level, or an average from its recent games. */
export interface TagEvidence {
  source: 'challenge' | 'match'
  challenge_id?: number
  challenge_name?: string | null
  level?: string
  percentile?: number | null
  metric?: string
  label?: string
  unit?: 'percent' | 'number' | null
  op?: '>=' | '<='
  value?: number | null
  threshold?: number
}

export interface PlaystyleTag {
  key: string
  label: string
  description: string
  polarity: 'positive' | 'negative'
  effects: PlaystyleEffect[]
  evidence?: TagEvidence | null
}

/** A tag as admins manage it. */
export interface AdminPlaystyleTag {
  id: number
  key: string
  label: string
  description: string
  polarity: 'positive' | 'negative'
  source: 'challenge' | 'match'
  rule: ChallengeRule | MatchRule
  effects: PlaystyleEffect[]
  enabled: boolean
  sort_order: number
  players: number                // how many players keep it
}

export interface ChallengeRule {
  challenges: { id: number; name: string }[]
  min_level: string
}

export interface MatchRule {
  metric: string
  op: '>=' | '<='
  value: number | null
  lanes: Partial<Record<Lane, number | null>>   // lane override; null: the tag does not apply in that lane
}

export interface PlaystyleOptions {
  hooks: { hook: string; kind: 'multiplier' | 'reduction'; range: [number, number]; cap: number; label: string; help: string }[]
  metrics: { metric: string; label: string; unit: 'percent' | 'number'; how: string; benchmarks: Partial<Record<Lane, [number, number]>> | null }[]
  levels: string[]
  lanes: Lane[]
  max_tags: number
  challenges: { id: number; name: string; description: string; levels: string[] }[]
  challenges_error: string | null
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
  player: { name: string; role: Lane; secondary_role: Lane | null; age: number; region: string; aggr: number; aware: number; pos: number; dmg: number; cs: number; pool: number[]; tags?: string[] }
  riot: { game_name: string; tag_line: string; region: string }
  riot_ref: string
  analysis: {
    games: number
    raw_stats: Record<string, number>
    // the stat ceiling and floor for this rank and region (floor 0: none); region_offset is the points the region
    // takes off both (0 on the strongest region)
    rank: RiotRank & { budget: number; floor: number; region_group: string; region_rating: number; region_offset: number }
    fitted_to_budget: boolean
    raised_to_floor: boolean
    missing_pool_slots: number
    notes: string[]
    source: { queue: string; label: string; games: number; is_solo: boolean; tried: Record<string, number> }
    breakdown: Record<string, RiotMetric[]>
    fit: { budget: number; floor: number; total_before: number; total_after: number }
    tags?: { earned: PlaystyleTag[]; suggested: string[]; challenges_loaded: boolean }
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
  is_public?: boolean
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
  /** with ?game_id: why the team breaks that lobby's restrictions (empty when allowed) */
  rule_issues?: string[]
  /** with ?game_id: why the team can't be chosen for each side, given the other side's team (mirror clause) */
  mirror_issues?: Record<Side, string[]>
  over_budget: boolean
  over_budget_players: OverBudgetPlayer[]
  is_default?: boolean
  is_public?: boolean
  share_issues?: string[]
  hidden?: boolean
}

export interface LobbySettings {
  mode: 'SOLO' | 'MULTI' | 'CPU'   // SOLO: one person plays both sides; CPU: one person vs the CPU
  hide_player_data: boolean
  bans_enabled: boolean
  timers_enabled: boolean
  pick_seconds: number
  ban_seconds: number
  series_format: SeriesFormat
  /** fearless draft: champions picked earlier in a series can't be picked or banned again */
  fearless: boolean
  /** team restrictions: every player a ranked Riot import at or below this tier; stat total caps */
  max_rank: string | null
  max_player_total: number | null
  max_team_total: number | null
  /** no Riot account (or hand-made player name) twice on one team */
  duplicate_clause: boolean
  /** no player on both teams */
  mirror_clause: boolean
  ruleset: string
  ruleset_name: string
  /** the creator changed some options from the ruleset's preset */
  ruleset_modified: boolean
}

/** Options a ruleset fills in on the create-lobby form. */
export interface RulesetSettings {
  hide_player_data: boolean
  bans_enabled: boolean
  timers_enabled: boolean
  pick_seconds: number
  ban_seconds: number
  series_format: SeriesFormat
  fearless: boolean
  max_rank: string | null
  max_player_total: number | null
  max_team_total: number | null
  /** no Riot account (or hand-made player name) twice on one team */
  duplicate_clause: boolean
  /** no player on both teams */
  mirror_clause: boolean
}

export interface Ruleset {
  key: string
  name: string
  description: string
  settings: RulesetSettings
}

/** GET /lobbies/rulesets */
export interface RulesetList {
  rulesets: Ruleset[]
  rank_tiers: string[]
  default: string
}

export type SeriesFormat = 'BO1' | 'BO3' | 'BO5'

/** The series as seen from one game: every side here is that game's Blue/Red. */
export interface SeriesState {
  id: number
  format: SeriesFormat
  wins_needed: number
  fearless: boolean
  game_number: number
  score: Record<Side, number>
  complete: boolean
  abandoned: boolean
  /** the side (in this game) of the team that won the series */
  series_winner: Side | null
  /** this game's losing side, once it is completed: they pick the side for the next game */
  loser_side: Side | null
  next_game_id: number | null
  next_ready: { blue: boolean; red: boolean }
  next_loser_side: Side | null
}

/** A finished game's rematch: both sides ready up, then a new lobby opens with the same settings, teams and sides. */
export interface RematchState {
  /** false mid-series: a rematch is only offered once the whole series is over */
  available: boolean
  ready: { blue: boolean; red: boolean }
  /** the rematch game, once it has started */
  game_id: number | null
}

/** Shown in match history. */
export interface SeriesSummary {
  id: number
  format: SeriesFormat
  fearless: boolean
  game_number: number
}

/** GET /series/{id}. Team keys name the side each team played in game 1. */
export interface SeriesResult {
  id: number
  format: SeriesFormat
  wins_needed: number
  fearless: boolean
  mode: 'SOLO' | 'MULTI'
  teams: Record<Side, string | null>
  score: Record<Side, number>
  winner: Side | null
  complete: boolean
  abandoned: boolean
  games: {
    game_id: number
    game_number: number
    status: GameStatus
    blue_team: Side
    red_team: Side
    winner: Side | null
    win_condition: 'NEXUS' | 'TIMEOUT' | null
    duration_seconds: number | null
    mvp: { player_id: number; name: string; champion: string; team: Side } | null
    draft: { bans: { team: Side; champion_id: number }[]; blue_picks: number[]; red_picks: number[] } | null
  }[]
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
  fearless_locked: number[]
}

export interface GameUser {
  /** null for the CPU's seat */
  id: number | null
  username: string
  /** the seat is played by the CPU */
  bot?: boolean
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
  /** the simulation seed once completed; it changes when the match is re-run */
  seed: number | null
  series: SeriesState | null
  /** set once the game is completed */
  rematch: RematchState | null
  /** set when the game is a season fixture's */
  season?: GameSeasonInfo | null
}

export interface LobbySummary {
  id: number
  code: string
  game_id: number
  status: GameStatus
  settings: LobbySettings
  expires_at: string
  you: Side | null
  series: SeriesSummary | null
}

export interface ResultPlayer {
  player_id: number
  name: string
  team: Side
  lane: Lane
  champion_id: number
  champion: string
  comfort_tier: string
  /** played outside the champion's usual roles (and not a top-3 pool pick): lane score penalty */
  off_role?: boolean
  lane_score: number
  kills: number
  deaths: number
  assists: number
  cs: number
  gold: number
  damage_dealt?: number           // missing on results simulated before damage was tracked
  damage_taken?: number
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
  comp: {
    win_rate: number
    damage_profile: { physical: number; magic: number }
    /** fraction of fight damage lost to one-sided damage; missing on results from before simulation 2.2.0 */
    damage_penalty?: number
    /** the comp's average same-team win rate minus the baseline, in points */
    ally_synergy?: number
    /** average champion scaling, 1 (early) to 3 (late); missing on results from before simulation 2.3.0 */
    scaling?: number
  }
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
  /** blue champion's win rate against the red one, from the against-team matrix */
  counter_rate?: number | null
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

export interface MatchupTeam {
  champions: number[]
  damage_profile: { physical: number; magic: number }
  /** fraction of fight damage lost to the enemy itemizing against a one-sided damage mix */
  damage_penalty: number
  totals: { damage: number; sturdiness: number; cc: number; mobility: number; utility: number; range: number; waveclear: number }
  /** average same-team win rate of the comp minus the baseline, in points */
  ally_synergy: number | null
  /** bot + support same-team win rate; null when there is no data */
  duo_win_rate: number | null
  /** average champion scaling, 1 (early) to 3 (late) */
  scaling: number
}
export type Attribute = 'Offence' | 'Defence' | 'Control'
export type LaneGrade = 'S' | 'A' | 'B' | 'C' | 'D' | 'F'
/** MAIN: the champion's most played role; SECONDARY: another usual role; OFF_ROLE_EXEMPT: off-role but a top
 * pool pick of the player's, so no penalty. null: the champion has no role data. */
export type RoleStatus = 'MAIN' | 'SECONDARY' | 'OFF_ROLE' | 'OFF_ROLE_EXEMPT' | null

/** The matchup wheel (Offence > Defence > Control > Offence) for one lane. */
export interface LaneWheel {
  blue: { strength: Attribute; weakness: Attribute }
  red: { strength: Attribute; weakness: Attribute }
  winner: Side | null
  kind: 'STRONG' | 'SLIGHT' | null
  /** each side's lane score multiplier after its coach's Draft */
  blue_multiplier: number
  red_multiplier: number
}

/** The multipliers behind a lane grade (each 1.0 when neutral), plus the comfort tier. */
export interface LaneFactors {
  comfort_tier: string
  comfort: number
  playstyle: number
  strength_fit: number
  off_role: number
  wheel: number
  counter: number
  duo: number
  range: number
  scaling: number
}

/** One side's player in a lane. Grade fields are null when that side's player data is hidden from you. */
export interface LaneAnalysis {
  player_id: number | null
  grade: LaneGrade | null
  /** 0..1: share of the champions they could play here that would score lower */
  percentile: number | null
  expected: number | null
  factors: LaneFactors | null
  role_status: RoleStatus
  /** fraction of lane score the off-role rule takes (0 when none); null when unknown */
  off_role_penalty: number | null
  /** average win rate against what this lane faces (bot and support: both enemy bot laners); null without data */
  counter_rate: number | null
}

export interface MatchupLane {
  blue: number | null
  red: number | null
  /** blue's win rate against red */
  blue_win_rate: number | null
  wheel: LaneWheel | null
  players: Record<Side, LaneAnalysis | null>
}

/** GET /games/{id}/matchups: what the drafted comps mean for the simulation. */
export interface MatchupPreview {
  teams: Record<Side, MatchupTeam>
  /** lane -> champion id per side, the opponent's included */
  lineups: Record<Side, Partial<Record<Lane, number>>>
  /** lane vs lane */
  lanes: Record<Lane, MatchupLane>
  /** false when the against-team matrix has no win rates at all */
  counter_data: boolean
  /** callouts when one side has a clear range or waveclear edge */
  notes: string[]
  settings: {
    win_rates_enabled: boolean
    baseline: number
    damage_balance_enabled: boolean
    damage_threshold: number
    max_damage_penalty: number
    champion_scaling_enabled: boolean
    off_role_enabled: boolean
    off_role_penalty: number
  }
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

/** Team notes for the team editor (POST /team-insights). */
export type TeamStyle = typeof STYLES[number]

export interface TeamNote {
  kind: 'strength' | 'weakness'
  title: string
  detail: string
  weight: number
}

export interface TeamInsights {
  filled: number
  stats: Record<'aggr' | 'aware' | 'pos' | 'dmg' | 'cs', number>
  typical_stat: number
  strengths: TeamNote[]
  weaknesses: TeamNote[]
  styles: { style: TeamStyle; label: string; score: number; pros: string[]; cons: string[] }[]
  suggested_styles: TeamStyle[]
  focus: { lane: Lane; gain: number; reason: string; power: number }[]
  suggested_focus: Lane[]
  comps: {
    style: TeamStyle
    label: string
    picks: Partial<Record<Lane, { champion_id: number; name: string; comfort: string; fit: number }>>
    damage: { physical: number; magic: number }
    scaling: number
    range: number
    notes: string[]
  }[]
  lanes: Partial<Record<Lane, { player: string; power: number; best: string }>>
}

export interface TeamInsightsRequest {
  style1: string | null
  style2: string | null
  focus1: string | null
  focus2: string | null
  coach_id: number | null
  roster: Partial<Record<Lane, number>>
}

/** A public item found by search: who shared it and when. */
export type Shared<T> = T & { owner: string; published_at: string | null }

/** Public team search results also carry the roster's stat total and average rank tier (0 = Iron). */
export type SharedTeam = Shared<Team> & { stat_total: number; average_rank: number | null }

export interface SearchPage<T> {
  total: number
  offset: number
  limit: number
  items: T[]
}

export type PublicKind = 'players' | 'coaches' | 'teams'

/** Search filters as query params: empty values are left out; arrays repeat the param. */
export type SearchFilters = Record<string, string | number | (string | number)[] | null | undefined>

// ---------------------------------------------------------------- seasons
export type SeasonStatus = 'SETUP' | 'PLAYER_DRAFT' | 'REGULAR' | 'PLAYOFFS' | 'COMPLETED' | 'CANCELLED'
export type CpuStrength = 'WEAKER' | 'EVEN' | 'STRONGER'
export type SeasonFormat = 'ROUND_ROBIN' | 'SWISS'
export type RosterMode = 'BYO' | 'DRAFT'

/** How a season's competition runs (the match rules are its `rules`). */
export interface SeasonOptions {
  team_count: number
  /** teams users manage; the CPU runs the rest */
  human_slots: number
  /** round robin: everyone plays everyone twice */
  rr_double: boolean
  regular_series: SeriesFormat
  cpu_strength: CpuStrength
  /** single elimination after the round robin (0: none); a Swiss stage always feeds a bracket of half the field */
  playoff_size: number
  playoff_series: SeriesFormat
  final_series: SeriesFormat
  /** Swiss only: wins to qualify / losses to go out */
  swiss_wins?: number
  swiss_losses?: number
  /** a round closes by itself this many hours after it opens (0 or missing: no deadline) */
  round_deadline_hours?: number
  /** Player Draft: seconds per pick before the best available player is picked automatically (0: no clock) */
  draft_pick_seconds?: number
  /** free agency: signings each manager may make over the season (0: off) */
  max_signings?: number
  /** free agents generated per lane when the competition starts */
  free_agents_per_role?: number
}

export interface SeasonTeamRef {
  /** the SeasonTeam id */
  id: number
  /** the season's frozen copy of the team */
  team_id: number
  name: string
  logo: string
  seed: number
  is_cpu: boolean
  is_you: boolean
  manager: { id: number; username: string } | null
}

export interface SeasonTeamSummary extends SeasonTeamRef {
  /** sum of the five players' stat totals */
  rating: number
}

export interface StandingRecord {
  seed: number
  rank: number
  played: number
  wins: number
  losses: number
  game_wins: number
  game_losses: number
  game_diff: number
  /** the current run: "W3", "L1" ("" before any match) */
  streak: string
  /** the last five results, oldest first */
  form: ('W' | 'L')[]
}

export interface StandingRow extends StandingRecord {
  team: SeasonTeamRef
  /** Swiss stage: decided yet? */
  swiss_status: 'QUALIFIED' | 'ELIMINATED' | null
  /** out of the season: missed the playoffs, out of the Swiss stage or knocked out */
  eliminated: boolean
}

export interface SeasonMatchGame {
  game_id: number
  game_number: number
  status: GameStatus
  winner_team_id: number | null
}

export interface SeasonMatch {
  id: number
  stage: SeasonStage
  round: number
  slot: number
  format: SeriesFormat
  status: 'SCHEDULED' | 'LIVE' | 'COMPLETED'
  /** how it was decided: played through the draft, or by the CPU for both sides */
  played_mode: 'LIVE' | 'AUTO' | null
  home: SeasonTeamRef | null
  away: SeasonTeamRef | null
  home_score: number
  away_score: number
  winner_team_id: number | null
  series_id: number | null
  live_game_id: number | null
  latest_game_id: number | null
  games: SeasonMatchGame[]
  /** a user manages one of the teams */
  has_manager: boolean
  /** you manage one of the teams */
  yours: boolean
  /** between two managers: which of them asked to let the CPU play it */
  auto_requested: { home: boolean; away: boolean }
  completed_at: string | null
}

export interface SeasonSummary {
  id: number
  name: string
  code: string
  status: SeasonStatus
  roster_mode: RosterMode
  format: SeasonFormat
  team_count: number
  teams_entered: number
  /** teams users manage, out of human_slots */
  managers: number
  human_slots: number
  current_round: number
  /** rounds in the current stage (Swiss: the most it can take) */
  total_rounds: number
  /** the stage being played; null before the start and after the end */
  stage: SeasonStage | null
  created_by: { id: number; username: string } | null
  is_creator: boolean
  /** your SeasonTeam id */
  my_team_id: number | null
  winner_team_id: number | null
  /** when the current round closes by itself (null: no deadline) */
  round_deadline_at: string | null
  created_at: string | null
  started_at: string | null
  completed_at: string | null
}

/** GET /seasons/{id}: the season hub */
export interface Season extends SeasonSummary {
  rules: RulesetSettings & { ruleset: string }
  options: SeasonOptions
  ruleset_name: string
  stage_label: string
  bracket: SeasonBracket | null
  my_team_eliminated: boolean
  teams: SeasonTeamSummary[]
  standings: StandingRow[]
  /** the current round's matches */
  round_matches: SeasonMatch[]
  my_match: SeasonMatch | null
  /** current round matches with a manager that are still unplayed */
  waiting_on_managers: number
  can_start: boolean
  can_advance: boolean
  /** the creator, while the season runs: may remove managers */
  can_manage: boolean
  champion: SeasonTeamRef | null
  /** Player Draft: the order, picks and who's on the clock (null before the draft and in Bring Your Own) */
  draft: SeasonDraft | null
  /** Player Draft setup: the pool so far */
  pool: SeasonPoolSummary | null
  free_agency: SeasonFreeAgency
  /** latest signings and releases, newest first */
  transactions: SeasonTransaction[]
}

export interface SeasonDraftPick {
  pick_number: number
  team: SeasonTeamRef | null
  player_id: number | null
  player_name: string
  lane: Lane
  /** made by the clock running out, the CPU or an auto-pick */
  auto: boolean
}

export interface SeasonDraft {
  order: (SeasonTeamRef | null)[]
  picks: SeasonDraftPick[]
  total_picks: number
  current_pick: number | null
  on_the_clock: SeasonTeamRef | null
  pick_deadline_at: string | null
  my_turn: boolean
  my_open_lanes: Lane[]
  complete: boolean
}

export interface SeasonPoolSummary {
  count: number
  /** players who can play each lane (a two-lane player counts in both) */
  by_lane: Record<Lane, number>
  /** what the pool can't fill for the managers entered so far */
  shortfall: Partial<Record<Lane, number>>
}

export interface SeasonFreeAgency {
  enabled: boolean
  max_signings: number
  /** the season is under way */
  open: boolean
  /** your team's, if you manage one */
  signings_left: number | null
}

export interface SeasonTransaction {
  id: number
  team: SeasonTeamRef | null
  type: 'SIGN' | 'RELEASE'
  player_id: number | null
  player_name: string
  lane: Lane
  stage: SeasonStage
  round: number
  created_at: string | null
}

/** GET /seasons/{id}/pool: the draft pool, or the free agents */
export interface SeasonPoolPlayer extends Player {
  lanes: Lane[]
  /** made up by the season (no owner) */
  generated: boolean
}

/** GET /seasons/join/{code}: what an invite shows before joining */
export interface SeasonJoinPreview {
  id: number
  name: string
  code: string
  status: SeasonStatus
  roster_mode: RosterMode
  format: SeasonFormat
  rules: RulesetSettings & { ruleset: string }
  options: SeasonOptions
  ruleset_name: string
  created_by: { id: number; username: string } | null
  managers: number
  open_slots: number
  is_member: boolean
  has_team: boolean
  can_join: boolean
}

export type SeasonStage = 'REGULAR' | 'SWISS' | 'PLAYOFF'

export interface SeasonBracketRound {
  round: number
  /** "Quarterfinals", "Semifinals", "Final" */
  name: string
  /** matches the round will have */
  slots: number
  format: SeriesFormat
  /** drawn so far, in bracket order (empty until the round starts) */
  matches: SeasonMatch[]
}

export interface SeasonBracket {
  size: number
  rounds: SeasonBracketRound[]
}

export interface SeasonSchedule {
  current_round: number
  stage: SeasonStage
  rounds: { stage: SeasonStage; stage_label: string; round: number; name: string; current: boolean; matches: SeasonMatch[] }[]
}

export interface SeasonPlayerStats {
  games: number
  kills: number
  deaths: number
  assists: number
  cs: number
  gold: number
  damage_dealt: number
  mvps: number
  kda: number
}

export interface SeasonTeamDetail {
  team: SeasonTeamRef
  view: Team
  record: (StandingRecord & { team: number }) | null
  matches: SeasonMatch[]
  /** by player id; empty while the season hides player data */
  player_stats: Record<string, SeasonPlayerStats>
}

/** On a game that belongs to a season fixture. */
export interface GameSeasonInfo {
  season_id: number
  season_name: string
  match_id: number
  stage: string
  round: number
  format: SeriesFormat
}

// ------------------------------------------------------------ season stats
/** One player's season line, summed from the box scores of every game they played. */
export interface SeasonPlayerStats {
  player_id: number
  name: string
  team_id: number
  team: SeasonTeamRef | null
  /** the lane they played most */
  lane: Lane | ''
  games: number
  wins: number
  mvps: number
  kills: number
  deaths: number
  assists: number
  cs: number
  gold: number
  damage_dealt: number
  kda: number
  /** average rank score: the same score that picks each game's MVP */
  rating: number
  kills_pg: number
  assists_pg: number
  deaths_pg: number
  cs_pg: number
  damage_pg: number
  champions: string[]
}

export interface SeasonLeaderRow {
  player_id: number
  name: string
  team_id: number
  team: SeasonTeamRef | null
  lane: Lane | ''
  games: number
  value: number
}

export interface SeasonLeaderCategory {
  key: 'rating' | 'kda' | 'kills_pg' | 'assists_pg' | 'cs_pg' | 'damage_pg' | 'mvps'
  label: string
  decimals: number
  rows: SeasonLeaderRow[]
}

export interface SeasonStats {
  games: number
  /** games a player needs to lead a stat or win an award (half the most anyone has played) */
  min_games: number
  /** the season is over: the awards are final (before that they show who leads the race) */
  final: boolean
  players: SeasonPlayerStats[]
  leaders: SeasonLeaderCategory[]
  awards: {
    season_mvp: SeasonPlayerStats | null
    finals_mvp: SeasonPlayerStats | null
    all_pro: { lane: Lane; player: SeasonPlayerStats | null }[]
  }
}

// ------------------------------------------------------------ notifications
export type NotificationKind =
  | 'MATCH_READY' | 'OPPONENT_READY' | 'AUTO_SIM_ASKED' | 'ON_THE_CLOCK' | 'DEADLINE'
  | 'SEASON_STARTED' | 'SEASON_OVER' | 'SEASON_JOINED' | 'SEASON_REMOVED'

export interface AppNotification {
  id: number
  kind: NotificationKind
  title: string
  body: string
  /** a path in the app, e.g. /seasons/3 */
  link: string
  season_id: number | null
  created_at: string | null
  read: boolean
}

export interface NotificationInbox {
  unread: number
  items: AppNotification[]
}
