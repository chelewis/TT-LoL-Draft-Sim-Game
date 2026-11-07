# League Draft Manager — Game Specification (v2)

This spec keeps the goals, platform, and architecture of `league_simulator_game_spec.md`, but replaces its generic "champion score" model with the data set in `Data/` and the simulation logic prototyped in `Game_Pick_Ban_Reference_Code.py`.

**What changed from the original spec:**

| Area | Original spec | This spec |
|---|---|---|
| What players control | Anonymous "Blue"/"Red" side | A **manager** of a named esports **team** with a 5-player roster that the manager builds and edits in a **team management** feature |
| Champion data | Invented stats (`early_game`, `scaling`, …) | `Champions.csv` (Damage, Sturdiness, CC, Mobility, Utility, Class, Style, Difficulty) + `ChampionStatistics.csv` |
| Lane assignment | Any champion to any lane | Champion is assigned to a **roster player**; the player's champion pool creates a **comfort** modifier |
| Simulation | Weighted score + variance | Phased simulation: lane phase → early game → mid game → late game, with skirmishes, objectives, gold, KDA, MVP |
| Winner | Highest score | The team that **destroys the enemy nexus** (towers → inhibitors → nexus towers → nexus). Gold only makes a team stronger along the way; it is not the win condition |

---

## 1. Overview

**League Draft Manager** is a browser-based two-player game. Each user builds teams and players in the management area, then picks a team for a lobby, drafts champions against the other user in a pick/ban phase, assigns the drafted champions to the players on their roster, and confirms. The backend then simulates the match and shows both users a match summary.

### Platform (unchanged)

- **V1:** responsive web app. **Future:** iOS / Android using the same API.
- **Backend:** Python (FastAPI). **Database:** PostgreSQL. **Auth:** token-based.
- **Real-time:** WebSockets for notifications; REST remains authoritative for mutations.

### Core Game Loop

```text
Login
  ↓
Create / Join Lobby
  ↓
Select Team (own team, or a default team)
  ↓
Both Players Ready
  ↓
Pick / Ban Phase
  ↓
Assign Drafted Champions to Roster Players (lanes)
  ↓
Both Players Confirm
  ↓
Simulate Match (lane → early → mid → late, until a nexus falls)
  ↓
Determine Winner, MVP, ACE, Player Rankings
  ↓
Display Match Results
```

---

## 2. Product Goals

Same goals as the original spec:

1. Let two users compete in a simulated League-style match.
2. Make pick/ban (and who plays what) the primary strategic mechanic.
3. Keep matches short and easy to understand.
4. Keep the simulation logical but with meaningful randomness.
5. Keep game rules/simulation independent of the web frontend.
6. Design the backend so a future mobile app can use the same API.

### Non-Goals for V1

Same as the original: no real-time movement, no item purchasing, no map rendering, no full League client, no voice chat, no spectators, no ranked matchmaking, no Riot account or live-data integration. The reference simulation is a **statistical** model; it must not grow into a real-time combat engine.

Also out of scope for V1: transfers/trading between users, player progression over time, and sharing/publishing teams to other users. Team, player, and coach creation and editing **is in scope** (§5.6).

---

## 3. IP / Data Consideration

The data set uses League of Legends champion names, and `Teams.csv` uses League-themed placeholder team names (e.g. "Team Demacia"). Before any public release, review Riot Games' IP and developer policies; the design keeps the engine independent of specific names:

- The engine operates on the numeric attributes in the CSVs, never on hard-coded champion names.
- All champion/team/player content lives in the data layer and can be replaced with original content without touching game logic.

---

## 4. Data Model (source: `Data/`)

The CSVs are the **seed data**. They are imported into PostgreSQL by a seed/migration script; the game reads from the database (or a cached in-memory copy), not from CSV at runtime. CSV column names below are as they appear today.

### 4.1 Champions — `Champions.csv` (155 rows)

| Column | Meaning |
|---|---|
| `Id`, `Name` | Identity |
| `Class` | Warrior, Mage, Assasin*, Marksman, Tank, Support, and hybrids (e.g. `Mage-Warrior`) |
| `Style` | 1–10 scale of damage split. 10 = fully magic, lower = more physical. Used to derive magic/physical damage |
| `Difficulty` | 1–3. Higher = bigger skill swing (see §9.3) |
| `DamageType` | `P`, `M`, or `PM` |
| `Damage`, `Sturdiness`, `Crowd-Control`, `Mobility`, `Utility` | Core combat attributes (roughly 1–3 each) |
| `Range` | 1 melee, 2 short range, 3 long range (see §9.5b) |
| `Waveclear` | 1 weak, 2 average, 3 strong (see §9.5b) |
| `Roles` | The champion's usual roles, most played first (typically its top 2 by pick rate; up to all 5): `top`, `jg`, `mid`, `bot`, `sup` separated by `\|` (e.g. `jg\|top`). Blank = no role data (see §9.5c) |

\* `Assasin` is misspelled in the data. Normalize to `Assassin` during import.

**Derived attributes** (computed once at load, not stored by hand):

```text
Offence  = Damage + Mobility
Defence  = Sturdiness + CC
Control  = Utility + CC

Strength = highest of Offence / Defence / Control
           (ties resolved in order Offence > Defence > Control, as in the reference code)
Weakness = the type that beats this champion's Strength (see matchup wheel, §9.4)
```

### 4.2 Champion Statistics — `ChampionStatistics.csv` (166 rows)

`Champion, WinRate, PickRate`. Joined to champions by **name**.

- `WinRate` feeds the team composition win rate shown in the draft summary.
- **Data issues to fix at import:** 2 champions (`Dr.Mundo`, `Nunu`) have no stats row; the stats file has extra rows with no champion. Join by a stable key (add `ChampionId` to the stats file) and default missing win rate to 50.0.

### 4.3 Players — `Players.csv` (12 rows)

| Column | Meaning |
|---|---|
| `ID`, `Name`, `Role`, `Age`, `Region` | Identity (`Role` ∈ top, jg, mid, bot, sup) |
| `aggr` | Aggression |
| `aware` | Awareness / map & objective sense |
| `pos` | Positioning |
| `dmg` | Damage output skill |
| `cs` | Farming skill (CS per minute) |

Stats are on a 1–10 scale.

### 4.4 Player Champion Pools — `PlayerChampionPools.csv`

`PlayerId, ChampionId1 … ChampionId5`. Ordered by preference; determines **comfort** (§9.2).

### 4.5 Teams — `Teams.csv` (10 rows)

| Column | Meaning |
|---|---|
| `ID`, `Name`, `Logo`, `Region`, `Fanbase` | Identity / flavor |
| `Style1`, `Style2` | Team playstyle: `early`, `scaling`, `teamfight`, `skirmish` |
| `Focus1`, `Focus2` | Preferred lanes: `top`, `jg`, `mid`, `bot`, `sup` |

### 4.6 Team Rosters — `TeamRosters.csv`

`TeamID, Top, Jungle, Mid, Bot, Supp, Coach` — each cell is a `Players.ID` / `Coaches.ID`.

**Data gap:** only teams 1 and 2 have rosters, and only 12 players exist (2 full rosters plus 2 spare mids). The CSVs therefore seed only **default (system) teams**: teams 1 and 2 are playable defaults; teams 3–10 are imported without rosters and are not selectable. Users fill the rest through the team management feature (§5.6), which replaces the need to author more CSV content.

### 4.7 Coaches — `Coaches.csv`

`ID, Name, Draft, Synergy` (both 1–10). Unused in the reference code; effects are defined in §5.4.

### 4.8 Database Entities

Original entities (`users`, `lobbies`, `games`, `game_players`, `draft_actions`, `team_lineups`, `match_results`, `match_lane_results`) are kept, plus seed-data tables and new fields:

```text
champions              (id, name, class, style, difficulty, damage_type,
                        damage, sturdiness, crowd_control, mobility, utility,
                        win_rate, pick_rate, enabled)
players                (id, owner_user_id NULL=system, name, role, age, aggr, aware, pos, dmg, cs, region)
player_champion_pools  (player_id, tier_position 1-5, champion_id)
teams                  (id, owner_user_id NULL=system, name, logo, style1, style2, focus1, focus2,
                        fanbase, region, coach_id, created_at, updated_at)
team_rosters           (team_id, lane, player_id)          -- one row per lane
coaches                (id, owner_user_id NULL=system, name, draft, synergy)
lobbies                + settings JSONB   -- e.g. {"hide_player_data": true}
game_team_snapshots    (game_id, team, snapshot JSONB)   -- frozen team, roster, players, pools, coach

games                  + blue_team_id, red_team_id, simulation_version, seed, hide_player_data
team_lineups           team, lane, champion_id, player_id  (player_id is new)
match_results          + win_condition, duration_seconds, mvp_player_id, ace_player_id, blue_kills, red_kills, blue_gold, red_gold,
                         blue_towers, red_towers, blue_dragons, red_dragons,
                         blue_barons, red_barons, blue_inhibs, red_inhibs, simulation_version
match_player_results   game_id, player_id, champion_id, lane, lane_score,
                         kills, deaths, assists, cs, gold, rank
match_events           game_id, sequence, phase, event_type, payload (JSONB)
```

`match_events` stores the narrative log (skirmishes, kills, objectives). Print statements in the reference code become structured events.

**Snapshots:** when a game leaves team selection, both teams are copied into `game_team_snapshots`. The game, the simulation, and the result screen use only the snapshot, so a manager editing a team or player afterwards (or mid-game) can never change an in-progress or historical game.

**Integrity rules** (in addition to the original spec): a roster has exactly 5 players, one per lane; a champion appears at most once per game (pick or ban); each roster player is assigned exactly one champion; a lineup's champion set must equal that team's picks.

---

## 5. Users, Teams, and Game States

### 5.1 Lobby and team selection

Lobby creation/joining, lobby code, 30-minute expiry, and the two-player limit are unchanged from the original spec. New step after both players have joined:

- Each player selects a **team** they own or a default (system) team, provided it has a complete, valid roster (§5.6). There is **no restriction** on both players choosing the same team (mirror matches are allowed).
- Blue side is the lobby creator; Red is the joiner (unchanged).
- Team selection is locked once both players click ready; at that point both teams are snapshotted (§4.8).

**Lobby settings** (chosen by the creator at lobby creation, stored in `lobbies.settings`):

| Setting | Default | Effect |
|---|---|---|
| `hide_player_data` | `false` | When `true`, the opponent's player stats and champion pools are hidden during the draft and lineup phases (see §5.3). Everything is revealed on the result screen |
| `bans_enabled` | `true` | When `false`, every ban phase is skipped: the draft is the 10 picks only, in the configured pick order |
| `timers_enabled` | `true` | When `false`, picks and bans have no time limit and no automatic action is ever taken |
| `pick_seconds` | `30` | Time limit per pick, 5-600 seconds, entered by the lobby creator (used when timers are enabled) |
| `ban_seconds` | `30` | Time limit per ban, 5-600 seconds (used when timers and bans are both enabled) |

### 5.2 State machine

```text
WAITING_FOR_PLAYERS → TEAM_SELECTION → READY_CHECK → DRAFTING
    → LANE_ASSIGNMENT → READY_TO_SIMULATE → SIMULATING → COMPLETED
                        (any state) → CANCELLED
```

The backend is authoritative for all transitions.

### 5.3 Draft

Unchanged from the original spec (§7–9): configurable action sequence, backend-owned timer (default 30 s), random legal action on timeout, availability validation.

The sequence matches the reference code (3 bans each → 6 picks → 2 bans each → 4 picks):

```json
{
  "draft_type": "STANDARD",
  "actions": [
    "BLUE_BAN", "RED_BAN", "BLUE_BAN", "RED_BAN", "BLUE_BAN", "RED_BAN",
    "BLUE_PICK", "RED_PICK", "RED_PICK", "BLUE_PICK", "BLUE_PICK", "RED_PICK",
    "BLUE_BAN", "RED_BAN", "BLUE_BAN", "RED_BAN",
    "RED_PICK", "BLUE_PICK", "BLUE_PICK", "RED_PICK"
  ]
}
```

That is 10 bans + 10 picks = 20 actions, 5 champions per team.

> The original spec's example sequence had only 14 actions (fewer bans). Use the 20-action sequence above as the V1 default since it is what the reference code implements; it remains a config value.

**Draft information shown to the drafter** (from data, helps the strategy layer):

- Own roster with each player's stats and 5-champion pool (always visible to their own manager)
- Champion attributes, class, damage type, win rate, pick rate
- Running **composition summary** for both teams: damage profile (physical vs magic), total sturdiness / CC / mobility / utility, average champion win rate
- Whether a champion is in one of the player's pool tiers (comfort preview)

**Opponent visibility depends on the `hide_player_data` lobby setting:**

- `false` (default): the opponent's roster, player stats, and champion pools are visible (esports scouting).
- `true`: the opponent's player stats and champion pools are hidden; only the team name, playstyle, and roster names/roles are shown. The server must not include the hidden fields in any API or WebSocket payload (not just hide them in the UI). There is no way to reveal it during the game; it is shown on the result screen.

In both modes the opponent's **lineup assignments** are hidden until both managers confirm. The champion picks and bans themselves are always public.

### 5.4 Coaches

Every team has one coach. `Coaches.Draft` and `Coaches.Synergy` (1–10) were unused in the reference code; V1 defines and enables them. Both are config-tunable (§11).

- **Draft** → *drafting skill*, a **simulation-only** effect (it has no effect on the draft UI, timer, or any other feature). It scales the team's lane-matchup advantages (§9.4): a matchup multiplier's bonus is multiplied by `1 + (draft − 5) * draft_matchup_scale` (default scale 0.05, so Draft 10 turns a 1.25 matchup edge into about 1.31, and Draft 1 into about 1.20). Disadvantaged matchups are not made worse.
- **Synergy** → *team cohesion*. Scales lane-assist fractions (§9.8) and the team style bonuses (§9.6) by `1 + (synergy − 5) * synergy_scale` (default scale 0.02, so Synergy 10 = +10%, Synergy 1 = −8%).

### 5.5 Lane assignment

After the draft each manager has 5 champions and a fixed roster (top, jg, mid, bot, sup). The manager **assigns each champion to a roster player**. This is the reference code's "swap" step (`Swap`, `SetChampionPicksFromRoster`).

- Exactly one champion per player, one player per champion.
- The manager sees the live **comfort** result of each pairing (§9.2) before confirming.
- Desktop: drag champion → player. Mobile: tap champion, then tap player.
- Assigning a champion away from its natural lane is legal; the champion attributes decide the consequences through the lane score formula (no separate "role suitability" penalty in V1).

Both managers must confirm; lineups are hidden from the opponent until both are confirmed.

### 5.6 Team management (new feature)

Logged-in users manage their own content outside of any lobby. This replaces filling out the remaining CSV rosters by hand.

**Managers can:** create, view, edit, and delete their own **teams**, **players**, and **coaches**; assign players to a team's five lane slots; set each player's five-champion pool; set team playstyle and lane focus; duplicate a default (system) team or player into their own account as a starting point. Default (system) content is read-only and visible to everyone.

**Player** fields: name, role, age, region, `aggr`, `aware`, `pos`, `dmg`, `cs`, and an ordered pool of exactly 5 distinct champions (a player never has more than 5; position 1 = best, §9.2).
**Team** fields: name, logo, region, fanbase, `style1`/`style2` (two distinct values from `early`, `scaling`, `teamfight`, `skirmish`), `focus1`/`focus2` (distinct lanes or none), coach, and exactly five roster slots (TOP, JUNGLE, MID, BOT, SUPPORT).
**Coach** fields: name, `draft`, `synergy`.

**Balance rules (server-enforced, values in config):**

- Each player stat is an integer 1–10.
- **Soft stat ceiling:** `aggr + aware + pos + dmg + cs` has a soft ceiling of `player_stat_budget` (default **32**). Users **may exceed it** on custom players (each stat is still capped at 10, so the absolute maximum is 50); the server does not reject the save. The Player Editor shows the running total and a warning when it goes over. Default (system) players are exempt from the flag even though some total up to 36.
- **Ceiling by rank:** a player imported from a ranked Riot account uses the ceiling for the rank it had when imported (`rank_stat_budgets`): Iron–Bronze **28**, Silver–Platinum **32**, Emerald–Diamond **36**, Master–Grandmaster **40**, Challenger **48**. Hand-made players and unranked imports use `player_stat_budget`. The rank only sets the ceiling the imported stats are fitted to and flagged against; it never raises stats that are already under it.
- **Region strength:** a Riot import's ceiling and floor are also lowered by its server's strength (`region_ratings`, out of `region_max_rating` 10): Korea **10**, China **8** (no public Riot platform yet), EU (EUW only) **7**, NA **6**, BR **5**, every other server **4**. Each point below 10 takes 1 point off both the ceiling and the floor (the floor never goes below 0; unranked imports still have no floor). So NA Challenger has ceiling 44 / floor 36, above KR Master's 40 / 36 ceiling: a top player on a weaker server can still out-rate a lower rank on a stronger one. Hand-made players are unaffected. The region used is the Riot platform from the signed import, not the editable `region` field.
- **Floor by rank:** when a ranked Riot account is imported and its stats total less than the floor for its rank (`rank_stat_floors`), they are scaled up proportionally to exactly the floor: Iron–Bronze **10**, Silver–Diamond **28**, Master–Grandmaster **36**, Challenger **40**. Hand-made players and unranked imports have no floor. The floor only shapes the imported numbers; the user may lower them in the editor and nothing is flagged.
- **Over-budget flag ("potentially illegal team"):** a team is flagged `over_budget` when any custom player on its roster exceeds the ceiling. The flag is computed by the server (never trusted from the client), stored in the game snapshot (§4.8), and shown as a warning icon plus notice on that team:
  - on the team in My Teams and the Team Editor;
  - in the lobby, on the team card visible to **both** players, with a tooltip listing which players are over budget and by how much;
  - on the draft, lineup, and result screens.
  The flag is informational only in V1: it never blocks a lobby, the draft, or the simulation, and it has no gameplay effect. It exists so that opponents can see when a team may not be legal under an agreed set of house rules. Setting `management.enforce_budget = true` in config would turn the ceiling into a hard limit later.
- Coach budget: `draft + synergy ≤ coach_stat_budget` (default 12; the seed coach totals 10).
- A roster slot's player must have that slot's role (`allow_off_role_roster = false` by default).
- A player may appear in only one slot of a given team, and champion pools have no duplicates.
- A team is **selectable** (usable in a lobby) only when it has all five slots filled, a coach, and valid styles.
- Per-user limits (default 20 teams, 100 players, 10 coaches) to keep the database bounded.

Editing or deleting a team/player that is part of an in-progress game is allowed, because games use snapshots (§4.8). Deleting a player that belongs to a team removes them from that team's roster and makes the team unselectable until refilled.

**Screens:** My Teams (list), Team Editor (roster slots, styles, focus, coach), My Players (list), Player Editor (stats with remaining budget, champion pool picker with champion attributes and win rate), My Coaches.

---

## 6. Architecture (unchanged, with one addition)

Keep the original layering: API → services → **game engine** → repositories → PostgreSQL, plus WebSockets. Additions:

```text
backend/app/game/
├── draft_engine.py       # sequence, validation, timeout action
├── comfort.py            # pool tier → comfort modifier
├── champion.py           # derived Offence/Defence/Control, Strength/Weakness
├── matchup.py            # Offence > Defence > Control wheel
├── lane_phase.py         # lane scores, lane gaps, gold diffs
├── skirmish.py           # SimulateFight equivalent
├── objectives.py         # dragons (soul, elder), barons
├── structures.py         # towers, inhibitors, nexus, siege rules, win condition
├── simulation_engine.py  # orchestrates phases, returns MatchResult
├── ranking.py            # KDA, MVP, player ranks
└── config.py             # every constant listed in §11
backend/app/services/team_management_service.py   # CRUD + budget/validation rules (§5.6)
backend/app/data/seed/    # the CSVs + seed loader for default (system) content
```

The engine must be **pure**: input = two `TeamSetup` objects + seed + config; output = `MatchResult`. No pandas DataFrames, no global state, no `print` — see §12.

---

## 7. API

Same base path `/api/v1` and endpoint groups as the original spec. Changes/additions:

```http
GET  /api/v1/champions                         # champions + derived attributes

# Team management (§5.6) — owner-only for writes; default content is read-only
GET    /api/v1/teams                           # own + default teams (?selectable=true to filter)
POST   /api/v1/teams
GET    /api/v1/teams/{team_id}
PUT    /api/v1/teams/{team_id}                 # name, styles, focus, coach, roster slots
DELETE /api/v1/teams/{team_id}
GET    /api/v1/players                         # own + default players
POST   /api/v1/players
GET    /api/v1/players/{player_id}             # stats + champion pool
PUT    /api/v1/players/{player_id}
DELETE /api/v1/players/{player_id}
GET    /api/v1/coaches   POST /api/v1/coaches   PUT/DELETE /api/v1/coaches/{coach_id}
POST   /api/v1/teams/{team_id}/duplicate       # copy a default team/players into own account

# Lobby / game
POST /api/v1/lobbies                           # body includes settings {hide_player_data}
POST /api/v1/lobbies/{lobby_id}/team           # choose team (any selectable team; no uniqueness rule)
PUT  /api/v1/games/{game_id}/lineup            # body: [{lane, champion_id}]  (player inferred from roster lane)
GET  /api/v1/games/{game_id}/lineup/preview    # comfort per pairing for the caller's own lineup
GET  /api/v1/games/{game_id}/result            # full result incl. events
GET  /api/v1/games/{game_id}/result/events     # paged narrative log
```

Game and draft payloads must omit hidden opponent player data when `hide_player_data` is set. `PUT /lineup` and the preview endpoint must reject requests for the opponent's lineup. All validation rules from the original spec (§24) apply.

New WebSocket events: `TEAM_SELECTED`, plus the original set. `SIMULATION_COMPLETED` carries only `game_id`; clients fetch the result over REST.

---

## 8. Simulation Overview

The reference code models a match in phases. The rewrite keeps the phase structure and the formulas, but is deterministic for a given seed.

```text
1. Setup            derive champion attributes, comfort, team composition totals
2. Lane phase       one lane score per player, matchup multipliers, lane gaps, gold diffs
3. Early game       (0–15 min)  dragons, towers, skirmishes
4. Mid game         (15–25 min) CS update, dragons, barons, towers, skirmishes
5. Late game        (25–35 min) larger fights, barons, elder dragon, sieges toward the nexus
6. Overtime         (only if no nexus has fallen by 35 min) repeated late-game rounds
7. Result           winner (nexus), MVP, ACE, player ranks, stats
```

The simulation runs the phases in order and **stops immediately when a nexus is destroyed**, so a game can end during mid game or late game.

### 8.1 Late game (implemented)

`SimulateLateGame()` in the reference code is only a stub of print statements (towers/drags/barons, teamfights, skirmishes, gold leads, objective/vision/jungle control, late-game picks). V1 implements it as a **third phase** that reuses the same building blocks as mid game, with these differences:

| Aspect | Mid game (15–25 min) | Late game (25–35 min) |
|---|---|---|
| CS | `UpdateCS` to 25 min | `UpdateCS` to 35 min |
| Skirmish size | 2–5 | 3–5 |
| **Teamfights** | none | 0–3 five-vs-five (or 4v5) teamfights; the reference rolls a `teamfights` count but never uses it — now used, run through the same fight function |
| Dragons | max 2 | max 2; once a team holds **soul**, further dragons are **Elder** (§9.10) |
| Barons | max 1 | max 2 |
| Sieges | possible | more likely (baron power plays, higher kill counts); the phase where nexus towers and the nexus are normally reachable |
| Scaling style | half bonus | full bonus (§9.6) |

The phase list, per-phase limits, and durations live in config (§11), so phases can be added or retuned without changing the orchestrator.

**Overtime.** If both nexuses are still standing at the end of the late-game phase, the simulation repeats short late-game rounds (default 5 minutes each, max 3, with barons and elder dragon available again). If no nexus has fallen after overtime, the game is decided by the **timeout tiebreaker** (§9.11). This is expected to be rare and is tracked in the balance suite.

---

## 9. Simulation Formulas

All numbers below are the reference code's values and are **tuning constants**, not rules. Each one must be read from `config.py`.

### 9.1 Lane score (per player)

```text
For each of aggr, aware, pos, dmg:
    roll_x = randint(1, 10) * player.x

Champion synergy weights (per champion; divisor 200):
    AggrSyn = (Damage*30 + Sturdiness*30 + CC*10 + Mobility*10 + Utility*20) / 200
    AwrSyn  = (Damage*10 + Sturdiness*30 + CC*20 + Mobility*10 + Utility*30) / 200
    PosSyn  = (Damage*30 + Sturdiness*20 + CC*10 + Mobility*30 + Utility*10) / 200
    DmgSyn  = (Damage*40 + Sturdiness*10 + CC*10 + Mobility*40 + Utility*20) / 200

score = roll_aggr*AggrSyn + roll_aware*AwrSyn + roll_pos*PosSyn + roll_dmg*DmgSyn
score = score * (1 + comfort_modifier)
score = score * strength_fit
score = score * matchup_multiplier

Strength fit (lane.strength_fit; champion strength = Offence / Defence / Control, §9.4):
    Offence -> avg(dmg, pos)    Defence -> aggr    Control -> aware
    strength_fit = 1 + 0.25 * (stat - 5.5) / 4.5     (x0.75 at 1, x1.0 at 5.5, x1.25 at 10)
```

This is where **player skill and champion identity interact**: an aggressive player on a high-damage/high-mobility champion scores much higher than the same player on a utility champion.

Every synergy weight is a positive mix of all five attributes, so on its own the sum favours champions with the highest attribute totals for every player. The strength fit is the counterweight: a player who is weak in the stats behind a champion's strength loses up to 25% on it, so the stat spread decides which champions suit a player.

### 9.2 Comfort

Based on where the assigned champion sits in the player's pool:

| Pool position | Tier | Reference value |
|---|---|---|
| `ChampionId1` | Best | +40 |
| `ChampionId2`, `ChampionId3` | Comfort | +25 |
| `ChampionId4`, `ChampionId5` | Familiar | +10 |
| Not in pool | Vulnerable | −10 |

A player's pool is always exactly 5 champions, ordered. Only the order matters for the boost; any champion outside the pool gets the −10% penalty.

Playstyle tags (§19.1) can change these values for one player: `off_pool_penalty` scales the Vulnerable penalty by `(1 − value)` (Champion Ocean halves it; One Trick makes it 50% worse) and `pool_best_bonus` scales the Best bonus by `(1 + value)`. The adjusted comfort feeds both the lane score and the fight skill check (§9.3).

**Unit correction required.** The reference code stores these as whole numbers and applies `score + score * comfortBuff`, which multiplies scores by 41× / 26× / 11× / −9×. That is clearly a bug (percent values used as fractions). The port must treat them as **percentages** (`+0.40`, `+0.25`, `+0.10`, `−0.10`) unless deliberate balancing says otherwise.

### 9.3 Difficulty and skill check

Used in fight performance (§9.7). Difficulty (1–3) widens the random swing of a player's performance on that champion:

```text
min_impact = comfort_modifier
max_impact = abs(comfort_modifier * difficulty)
skill_check = randint(min_impact, max_impact)      # in percent
performance *= (1 + skill_check / 100)
```

Comfortable pick on a hard champion = higher ceiling; unfamiliar pick = higher risk. (Guard `min_impact <= max_impact` — for negative comfort the reference code's `randint` bounds are reversed and would raise.)

### 9.4 Matchup wheel

```text
Offence beats Defence
Defence beats Control
Control beats Offence
```

For two opposing laners: if one champion's Strength equals the other's Weakness, the first has a matchup advantage.

```text
diff = winner.<Strength attribute> − loser.<Weakness attribute>
multiplier = 1.5 if diff >= 2 else 1.25       # otherwise 1.0
```

The result screen reports this as "Favours X Strongly / Slightly in lane" or "Even Matchup".

The team coach's **Draft** rating (§5.4) scales the *bonus part* of the multiplier for that team's favourable matchups: `1 + (multiplier − 1) * (1 + (draft − 5) * draft_matchup_scale)`.

> Ordering bug in the reference: `SetChampionLaneMatchupAdvantage` is called *after* lane scores are calculated (inside `OutputLaneResults`), so multipliers never affect the game. In the port, matchup multipliers are determined at lane-phase start (needs both lanes' champions, which are known after lineup lock) and **applied** to the score.

### 9.5 Team composition

Computed once at lineup lock:

```text
comp_damage, comp_sturdiness, comp_cc, comp_mobility, comp_utility = sums over 5 champions
damage_profile = [count of physical points, count of magic points]   # from DamageType, weighted by Damage
comp_win_rate  = mean of champion WinRate
```

Used for:
- Draft UI summary (both teams)
- **Damage balance:** a team whose damage leans on one type is easier to itemize against. Its fight damage is cut by `max_penalty * (share - threshold) / (1 - threshold)` once the main type's share passes `threshold` (defaults 0.65 and 0.25, so a single-type comp loses 25%), scaled by a per-phase weight (early 0.5, then 1.0). Sturdiness is unaffected.

### 9.5a Champion win rate matrices

The admin-edited same-team (`ally`) and against-team (`enemy`) matrices feed the simulation. A delta is the average win rate of a set of pairs minus `baseline` (50), capped at ±`max_points`. Pairs with no data are skipped. Each effect multiplies by `1 + scale * delta`:
- **Lane counter** (`lane_counter_scale`): each lane score, from the champion's win rate against its lane opponent. Bot and support each face both enemy bot laners.
- **Bot lane duo** (`lane_duo_scale`): bot and support lane scores, from their same-team win rate.
- **Fight synergy** (`fight_synergy_scale`): fight power, from the average same-team win rate among that side's fighters.
- **Fight counter** (`fight_counter_scale`): fight power, from the fighters' average win rate against the enemy fighters.

The `win_rates` and `damage_balance` constants can be edited on the admin Simulation Settings page. They are stored as overrides of `SIMULATION_CONFIG`, and each result records the overrides it was simulated with.

### 9.5b Range and waveclear

Pure multipliers and chance offsets (no rolls); most compare one side with the other, so equal comps are unaffected. Each section (`range`, `waveclear`) has an `enabled` switch and can be tuned on the admin Simulation Settings page. Code: `backend/app/game/range_waveclear.py`.

**Waveclear**
- **Lane CS** (`lane_cs_scale` 0.10): top, mid and bot lane-phase CS × `1 + scale * 2 * (share - 0.5)`, share = own waveclear / (own + lane opponent's). Strong vs weak = ±5%.
- **Farm speed** (`farm_scale` 0.04): from the end of the lane phase, CS per minute × `1 + scale * (waveclear - 2)`.
- **Objective priority** (`priority_scale` 0.05): objective control (dragons, barons, tower trades) × `1 + scale * (weighted waveclear - 2)`, lane weights `priority_weights` (mid 0.35, bot 0.25, top 0.2, jungle and support 0.1).
- **Sieges** (`siege_scale` 0.05): siege hit chance + `scale * (attackers' average waveclear - defenders')`.

**Range**
- **Lane trades** (`lane_scale` 0.03): lane score × `1 + scale * (own range - opponent's)`. Bot and support compare duo averages; the jungle is unaffected.
- **Teamfights vs skirmishes**: fight power × `1 + teamfight_scale * diff` (0.04, sides of 4+) or `1 - skirmish_scale * diff` (0.03, sides of 3 or fewer), diff = fighters' average range - enemy fighters'.
- **Siege poke** (`siege_scale` 0.05): siege hit chance + `scale * (attackers' average range - defenders')`.

The matchup panel shows both team totals and adds a callout when one team's total leads by 2+, when a top or mid laner out-ranges their opponent by 2 steps, or when a bot duo's average range leads by 1+. Callouts only mention effects that are switched on.

### 9.5c Off-role champions

Any champion can be played in any lane, but a champion played outside its `Roles` (typically its top 2 roles by pick rate) is discouraged: that player's lane score × `1 - lane_penalty` (0.15). The lane score carries into lane gold and fight performance, so the cost is felt over the whole game. **Exception:** no penalty when the champion is in the first `pool_exempt` (3) slots of the player's pool — a pocket pick they have mastered. A champion with no role data is never off-role. The `off_role` section (`enabled`, `lane_penalty`) can be edited on the admin Simulation Settings page; the CPU drafter reads the same rule. Code: `backend/app/game/comfort.py` (`off_role`, `off_role_multiplier`), applied in the lane phase.

The champion card in the draft shows its roles, the lineup step marks an off-role pick, and each result player has an `off_role` flag (shown as a badge).

### 9.6 Team style and focus (enabled in V1)

`Style1/Style2` and `Focus1/Focus2` are read but never applied in the reference code. V1 applies them as follows. Bonuses are multipliers (defaults: +10% for the primary style, +5% for the second; tune in config) and are scaled by the coach's Synergy (§5.4):

| Field | Proposed effect |
|---|---|
| `early` | + lane score in the lane phase and fight score in early-game skirmishes |
| `scaling` | + fight score and objective control: half in mid game, full in late game and overtime; a small penalty in the lane phase so scaling is a real trade-off |
| `teamfight` | + fight score when 4–5 players are involved (including all late-game teamfights) |
| `skirmish` | + fight score when 1–3 players are involved |
| `Focus1/2` lane | Bonus to the focused lane's score, and the team prefers sieging that lane (§9.11). Jungle/support focus boosts the assist fractions in §9.8 |

The strongest version of this feature ties it to the draft: drafting *against* your own team's style (e.g. picking poke for a `teamfight` team) is a deliberate strategic choice.

### 9.7 Skirmishes and fights

Per skirmish:

1. Pick attackers/defenders (random sample from each roster; size limits per phase — early 1–4 vs 1..n, mid 2–5 vs 1..n).
2. For each combatant compute `performance = (lane_score + champion_gold) / 2`, adjusted by the skill check (§9.3).
3. Accumulate team fight stats: Damage, Sturdiness, CC, Mobility, Utility.
4. Team combat modifier = mean of (CC, Mobility, Utility) per combatant, divided by 3.
5. `skirmish_score = own_damage * own_modifier − enemy_sturdiness * enemy_modifier`. Higher wins.
6. `execution_diff = |score_a − score_b| / 1,000,000` (constant configurable). Kills:
   - `execution_diff > enemy_combatants` → winner kills all, loser gets none
   - `execution_diff > 1` → winner kills `int(diff)`, loser kills `randint(0, winner_kills)`
   - otherwise 1–1 trade
   - equal scores → "ended even", small equal score for each team
7. Kill and death credit are drawn by weighted random choice (kill weight = fight performance; death weight = inverse of performance), without replacement for deaths.
8. Each kill gives 300 gold to the killer; each assist gives 150 gold to teammates in the fight. Update K/D/A and KDA.
9. Winning team's `mid_game_score` += number of enemy combatants (0.5 each on a draw).

Known issues to fix in the port: `execution_diff` uses a 1,000,000 divisor that makes most fights hit the "1–1 trade" branch — verify against real numbers before keeping it; in the "team 2 wins" branch the loop rolls team 1's deaths from `t1deathprob` but treats the loser's kills as the winner's — re-check the symmetry when refactoring into one function; and the kill/death crediting loop can spin forever if the survivors list and probability array go out of sync (use `numpy.random.Generator.choice` on the remaining pool with renormalized weights instead).

### 9.8 Lane gaps and assists

Lanes influence each other: each lane's score gains a fraction of the other lanes' scores (jungle 0.45, support-to-bot 0.5, others 0.10). Reference code has an index bug (`j == 5` never matches a 5-lane array) so the support→bot assist never triggers, and it *mutates* lane scores in place during the loop, so the order of lanes changes results. Port: compute all assist contributions from a snapshot of the original lane scores, then apply.

### 9.9 Gold and CS

```text
15-minute CS   = player.cs * 15          (support: * 0.15)
Gold from CS   = CS * 19.8
Lane bonus     = lane gold diff, added to the lane winner
Kill / assist  = +300 / +150
Tower          = +250 to a random top/mid/bot champion
Dragon soul    = +1000 to each champion on the claiming team
```

`UpdateCS(team1, team2, gametime)` recalculates CS for a later game time and adds the delta gold.

### 9.10 Objectives

- **Dragons**: total this phase = `randint(0, max_dragons)` (early 3, mid 2). Each dragon is assigned by weighted random using team **objective control** = `(sum(aware) + sum(pos)) * randint(1,3)`. Soul at 4 dragons (first to 4, if the enemy has none). Each dragon adds `dragons/10` to every player's lane score; soul gives ×1.5. Elemental pool is 7.
- **Barons**: per phase `randint(0, max_barons)` (mid 1, late 2, overtime round 1). Winner gets a power play: +50 objective control for the towers/dragon rolled immediately after, and the team's next siege (§9.11) gets extra structure hits.
- **Elder dragon**: after a team has claimed soul, later dragons are Elder. The team taking it gets a temporary fight-score bonus (`elder_bonus`, default +15%) for its next N fights (default 2).
- **Towers (objective rolls)**: phase max (early 5, mid 6, late 4) with decreasing probability per additional tower. Winner per tower by objective control. Each tower taken here follows the structure rules in §9.11 (lane towers only; inhibitors, nexus towers, and the nexus fall only through sieges). A team behind by more than 2000 gold gets a bounty (+250 gold and +600 lane score to each player) per tower taken.
- **Gold as strength:** team objective control is multiplied by `1 + gold_lead_pct * gold_control_scale` (default scale 1.0, lead capped at ±30%), so a gold lead makes objectives and sieges more likely but never ends the game by itself.
- **Heralds**: defined in the reference code but never called; exclude from V1.

Known issue: `np.random.choice(maxtowers, 1, towerprob)` passes the probabilities as the `replace` argument, so tower counts are uniform, not weighted. In the port, use the intended weights with `p=` and normalize them.

### 9.11 Win condition, structures, and timeout

**The team that destroys the enemy nexus wins.** Gold is *not* a win condition. It only determines how strong a team is at a given moment (fight performance, objective control, siege success), so it matters through everything it influences.

#### Structure model (per team)

```text
For each of TOP, MID, BOT:    tower 1 → tower 2 → tower 3 → inhibitor
Nexus towers (2):             attackable once at least one inhibitor is down
Nexus:                        attackable once both nexus towers are down
Total towers per team:        3 lanes × 3 + 2 nexus towers = 11   (matches towersRemaining = 11)
```

JUNGLE and SUPPORT have no lane structures; they matter through assist fractions, objective control, and fights. Structures within a lane must fall in order.

#### Siege

After a skirmish or teamfight, if the winning team killed at least `siege_min_kills` (default 2) — or has a baron power play — it makes a **siege attempt**:

1. Number of structure hits = `1 + (kills ≥ 4 ? 1 : 0) + (baron power play ? baron_extra_hits : 0)`, each hit scaled by the team's objective control ratio (which includes the gold-lead factor from §9.10).
2. Each hit picks a lane weighted by the team's lane-score lead in that lane (plus focus bonus, §9.6) and destroys that lane's next structure. If the lane is exhausted, or the nexus towers/nexus are unlocked, the hit goes to the next available structure by priority: inhibitor → nexus tower → nexus.
3. When a hit lands on the nexus, the game **ends immediately**; that team is the winner and the current phase minute is the game duration.

#### Timeout tiebreaker

If no nexus falls by the end of overtime, the winner is decided in this order: (1) more structures destroyed (tower = 1, inhibitor = 2, nexus tower = 2); (2) higher total team gold; (3) seeded coin flip. The result is marked `win_condition: "TIMEOUT"` instead of `"NEXUS"`.

`winner_rule` in config selects the rule set (`"nexus"` default) so alternatives can still be trialled.

### 9.12 MVP, ACE and ranking

```text
rank_score = int(lane_score * KDA)
KDA        = (kills + assists) / max(1, deaths)
```

Ranks are assigned across all 10 players by `rank_score`.

- **MVP** = the highest `rank_score` on the **winning** team.
- **ACE** = the highest `rank_score` of **all ten players**, regardless of team. If the ACE is on the winning team they are also the MVP; otherwise the result shows both (a losing-side ACE is a normal outcome).
- Ties break by kills, then by gold, then seeded coin flip.

---

## 10. Randomness and Determinism

The reference code calls Python `random` and NumPy random at global scope, so results cannot be reproduced. **Requirement:** one seeded `random.Random` / NumPy `Generator` is created per match from `game.seed` and passed through every function.

- Seed generated server-side at simulation start and stored on the game.
- Same `(blue_team, red_team, lineups, seed, simulation_version, config)` must reproduce the identical `MatchResult` and event log. Add a regression test that runs the same input twice.
- Persist `simulation_version` on every result (original spec §37).

---

## 11. Configuration

Everything numeric in §9 moves into config. Example:

```python
SIMULATION_CONFIG = {
    "version": "2.0.0",
    "comfort": {"best": 0.40, "comfort": 0.25, "familiar": 0.10, "vulnerable": -0.10},
    "lane": {
        "roll_range": [1, 10],
        "champion_synergy": {                     # weights sum per stat; divisor 200
            "aggr":  {"damage": 30, "sturdiness": 30, "cc": 10, "mobility": 10, "utility": 20},
            "aware": {"damage": 10, "sturdiness": 30, "cc": 20, "mobility": 10, "utility": 30},
            "pos":   {"damage": 30, "sturdiness": 20, "cc": 10, "mobility": 30, "utility": 10},
            "dmg":   {"damage": 40, "sturdiness": 10, "cc": 10, "mobility": 40, "utility": 20},
            "divisor": 200
        },
        "matchup_multiplier": {"slight": 1.25, "strong": 1.5, "strong_threshold": 2},
        "assist": {"jungle": 0.45, "support_to_bot": 0.5, "other": 0.10}
    },
    "economy": {"gold_per_cs": 19.8, "kill": 300, "assist": 150, "tower": 250,
                "soul_bonus": 1000, "support_cs_factor": 0.15, "starting_gold": 2500,
                "bounty_gold_deficit": 2000, "bounty_gold": 250, "bounty_lane_score": 600},
    "phases": [
        {"name": "early", "minutes": [0, 15],  "max_dragons": 3, "max_barons": 0, "max_towers": 5,
         "max_skirmishes": 10, "skirmish_size": [1, 4]},
        {"name": "mid",   "minutes": [15, 25], "max_dragons": 2, "max_barons": 1, "max_towers": 6,
         "max_skirmishes": 10, "skirmish_size": [2, 5]},
        {"name": "late",  "minutes": [25, 35], "max_dragons": 2, "max_barons": 2, "max_towers": 4,
         "max_skirmishes": 8,  "skirmish_size": [3, 5], "max_teamfights": 3, "teamfight_size": [4, 5]}
    ],
    "overtime": {"round_minutes": 5, "max_rounds": 3, "max_barons": 1, "max_dragons": 1,
                 "max_skirmishes": 4, "max_teamfights": 2},
    "objectives": {"dragon_soul_at": 4, "elemental_pool": 7, "baron_power_play_bonus": 50,
                   "elder_bonus": 0.15, "elder_fights": 2,
                   "gold_control_scale": 1.0, "gold_lead_cap": 0.30},
    "structures": {"towers_per_lane": 3, "nexus_towers": 2, "siege_min_kills": 2,
                   "baron_extra_hits": 2, "timeout_weights": {"tower": 1, "inhibitor": 2, "nexus_tower": 2}},
    "fight": {"execution_divisor": 1_000_000},
    "winner_rule": "nexus",
    "team_style": {"enabled": True, "primary_bonus": 0.10, "secondary_bonus": 0.05,
                   "scaling_lane_penalty": 0.05, "focus_lane_bonus": 0.08},
    "coach": {"draft_matchup_scale": 0.05, "synergy_scale": 0.02},
    "management": {"player_stat_budget": 32,
                   "rank_stat_budgets": {"IRON": 28, "BRONZE": 28, "SILVER": 32, "GOLD": 32, "PLATINUM": 32, "EMERALD": 36, "DIAMOND": 36,
                                         "MASTER": 40, "GRANDMASTER": 40, "CHALLENGER": 48},
                   "rank_stat_floors": {"IRON": 10, "BRONZE": 10, "SILVER": 28, "GOLD": 28, "PLATINUM": 28, "EMERALD": 28, "DIAMOND": 28,
                                        "MASTER": 36, "GRANDMASTER": 36, "CHALLENGER": 40},
                   "region_ratings": {"KR": 10, "CN": 8, "EU": 7, "NA": 6, "BR": 5, "OTHER": 4}, "region_max_rating": 10,
                   "region_groups": {"KR": "KR", "EUW1": "EU", "NA1": "NA", "BR1": "BR"},
                   "enforce_budget": False, "system_players_exempt": True, "champion_pool_size": 5, "coach_stat_budget": 12, "stat_range": [1, 10],
                   "allow_off_role_roster": False,
                   "max_teams_per_user": 20, "max_players_per_user": 100, "max_coaches_per_user": 10},
    "win_rates": {"enabled": True, "baseline": 50.0, "max_points": 10.0, "lane_counter_scale": 0.03, "lane_duo_scale": 0.02,
                  "fight_synergy_scale": 0.02, "fight_counter_scale": 0.02},
    "damage_balance": {"enabled": True, "threshold": 0.65, "max_penalty": 0.25,
                       "phase_weights": {"early": 0.5, "mid": 1.0, "late": 1.0, "overtime": 1.0}}
}
```

The draft config (`draft_timer_seconds`, `actions`, `lobby_expiration_minutes`, `lanes`) is unchanged from the original spec.

---

## 12. Porting the Reference Code — Required Refactors

`Game_Pick_Ban_Reference_Code.py` is a **prototype**. The following must change when it becomes the engine; none of these change the game's design:

| Issue in the reference | Required change |
|---|---|
| Module-level globals (`GameBans`, `T1Picks`, `ChampionObjects`, `GamePlayerRankings`, …) | State lives on a `MatchState` object; nothing global (a second match must not see the first's data) |
| `pandas` `.loc[...]` lookups inside hot loops | Load CSVs once into typed dataclasses / dicts |
| `print` for narrative | Emit structured `MatchEvent`s (`phase`, `type`, `payload`); UI renders text |
| Unseeded `random` / `np.random` | Single seeded RNG per match (§10) |
| `comfortBuff` unit bug (§9.2) | Percent → fraction (confirmed: +40% / +25% / +10% / −10%, not ×41) |
| `max(score, 100)` in `CalculateLaneScore2` | This is a floor of 100 on every lane score, which flattens weak performances (and hides the comfort penalty). Keep it as a floor if intended, but make `lane.min_score` configurable |
| Matchup multiplier applied after scoring (§9.4) | Apply before the phase begins |
| Lane assist index bug and in-place mutation (§9.8) | Snapshot then apply |
| `randint` bounds reversed for negative comfort (§9.3) | Order the bounds |
| `np.random.choice(maxtowers, 1, towerprob)` (§9.10) | Use `p=` |
| `GetMVP` picks best of both teams | Winning-team MVP plus overall ACE (§9.12) |
| Hard-coded main run with picked IDs | Replaced by lobby/draft flow |
| `GetWinner` compares total gold; `towersRemaining`/`inhibsExposed` are tracked but never decide anything | Winner = nexus (§9.11); gold is strength only; structures modeled per lane in `structures.py` |
| `Coaches`, team style/focus unused; heralds unused | Coach and style/focus are implemented (§5.4, §9.6); heralds stay out of V1 |
| `SimulateLateGame` stub | Implemented per §8.1 |
| Team ids/roster hard-coded in `MyTeam(1,1,2,3,4,5)` | Read from `team_rosters` |

Also add an **outlier check** to the balancing suite: with unseeded lane rolls, comfort ×41 (the current bug) makes results essentially independent of the draft, which defeats the purpose of the game.

---

## 13. Result and Summary

Extends the original result screen (§19–20):

```json
{
  "game_id": "game-123",
  "simulation_version": "2.0.0",
  "seed": 4928191,
  "winner": "BLUE",
  "win_condition": "NEXUS",
  "duration_seconds": 1980,
  "mvp": {"player_id": 3, "name": "DC God", "champion": "Ahri", "team": "BLUE"},
  "ace": {"player_id": 8, "name": "Tehbezt", "champion": "Orianna", "team": "RED"},
  "teams": {
    "BLUE": {"gold": 61234, "kills": 17, "towers": 11, "inhibitors": 2, "dragons": 3, "barons": 1, "soul": false,
             "comp": {"win_rate": 50.8, "damage_profile": {"physical": 9, "magic": 14}}},
    "RED":  {"gold": 55901, "kills": 11, "towers": 3, "inhibitors": 0, "dragons": 1, "barons": 0, "soul": false,
             "comp": {"win_rate": 49.9, "damage_profile": {"physical": 16, "magic": 6}}}
  },
  "lanes": {
    "TOP": {"blue_player": 1, "red_player": 6, "blue_champion": 68, "red_champion": 109,
            "blue_score": 812, "red_score": 640, "matchup": "Favours X Strongly in lane.",
            "gold_diff": 172, "winner": "BLUE"}
  },
  "players": [
    {"player_id": 1, "team": "BLUE", "champion_id": 68, "kills": 4, "deaths": 1, "assists": 6,
     "cs": 210, "gold": 14200, "kda": 10.0, "rank": 2, "comfort_tier": "COMFORT"}
  ],
  "events_available": true
}
```

The summary text should explain the outcome using this data (lane wins, objective lead, comfort mismatches, matchup advantages, fight results) without exposing formula details. Examples:

> Blue won top and mid lanes with strong matchup advantages, then converted the gold lead into three dragons and a baron siege that ended the game at 33:00.

> Red's bot laner was on an off-pool champion, costing them the lane.

**Screens:** Login, Home, Create/Join Lobby, Team Select, Lobby, Draft, Lane Assignment (with comfort preview), Simulation (event feed, optionally revealed progressively for tension — the result is already computed), Match Results (team stats, structures destroyed, lane breakdown, per-player scoreboard, MVP and ACE), Team Management (My Teams / Team Editor / My Players / Player Editor / My Coaches), Profile/Settings. The Create Lobby screen includes the `hide_player_data` toggle.

---

## 14. Everything Else Carries Over

The following sections of `league_simulator_game_spec.md` apply unchanged (replace "champion score" with the model above where relevant):

- State synchronization and reconnection (§31–33)
- Security and anti-cheat (§34–35) — note the **lineup preview** endpoint must never reveal the opponent's assignments
- Observability, simulation versioning, analytics (§36–38)
- Testing strategy (§39), with the additions below
- Future features (§43) and development principles (§44)

### Additional tests

- **Data loading:** all CSV rows import; referential integrity (rosters → players, pools → champions); team without a complete roster is not selectable.
- **Team management:** stat range enforced server-side; players over the soft ceiling save successfully but set the team's `over_budget` flag (with per-player detail); the flag appears in lobby, draft, lineup and result payloads for both managers and is computed from the snapshot; default players never trigger it; role-slot matching; duplicate pool champions rejected; a user cannot read-write another user's teams/players; default content is read-only; deleting a rostered player makes the team unselectable; per-user limits; edits after game start do not change the snapshot.
- **Hidden data:** with `hide_player_data = true`, opponent stats/pools never appear in any REST or WebSocket payload until the game ends. **Coach Draft:** changes only the simulation's matchup multipliers and nothing else (a draft-rating change must not alter timers, payloads, or the draft flow).
- **Structures / win condition:** structures fall in order per lane; nexus towers locked until an inhibitor is down; nexus locked until both nexus towers are down; the simulation stops the moment the nexus falls; exactly one winner; duration matches the ending event; timeout tiebreaker order (structures → gold → coin).
- **Late game:** late phase and overtime run only when no nexus has fallen; late-game teamfights use the fight function; elder dragon only after soul.
- **MVP / ACE:** MVP is always on the winning team; ACE is the global max; both present in every result.
- **Derived attributes:** Strength/Weakness for every champion; matchup wheel is cyclic (each type beaten by exactly one other).
- **Comfort:** each pool position maps to the right tier; off-pool is vulnerable.
- **Determinism:** same inputs + seed → identical `MatchResult` and event sequence.
- **Invariants:** total kills = total deaths; gold ≥ 0; each player has exactly one champion; towers taken ≤ 11 per side; dragons ≤ pool; soul only claimed once.
- **Balance suite (Phase 7):** run N (e.g. 10,000) seeded simulations per scenario and check:
  - Same teams, random drafts: win rate stays within a target band (no side or team dominates)
  - Best-tier pool picks vs off-pool picks: win rate meaningfully above 50% (drafting matters)
  - Strong-matchup vs neutral: measurable edge
  - Average kills, gold, tower counts look plausible
  - Random seed variance still yields upsets (≈ 30–40% for the weaker side in a mid-strength mismatch; tune to taste)
  - Game length and endings: median game length in the 25–35 min range; ≥ 90% of games end by nexus (timeouts are rare); essentially no game ends before ~15 minutes
  - Gold matters but does not decide: teams with a 5k+ gold lead at 25 min win noticeably more often, yet not near 100%
  - Style bonuses: `scaling` teams do better the longer the game runs; `early` teams do better in short games
  - Budget-maxed custom teams vs default teams stay within a target win-rate band

---

## 15. MVP Acceptance Criteria

All criteria from the original spec (§40), plus:

### Data
- [ ] All seed CSVs import into the database with validation as default (system) content.
- [ ] Champion derived attributes (Offence/Defence/Control, Strength/Weakness) are computed correctly.
- [ ] At least two default teams with complete rosters are selectable.

### Team Management
- [ ] A user can create, edit, and delete their own teams, players, and coaches.
- [ ] Stat range, role-slot, pool, and limit rules are enforced by the server; the stat ceiling is soft.
- [ ] Teams with over-budget custom players show a "potentially illegal team" icon/notice to both players in the lobby.
- [ ] Default content is read-only and can be duplicated.
- [ ] Only complete, valid teams can be chosen for a lobby.

### Lobby Settings
- [ ] The lobby creator can toggle `hide_player_data`.
- [ ] With it on, opponent player data is absent from all payloads until the game ends.
- [ ] Coach Draft rating affects only simulation matchup strength.

### Team & Lineup
- [ ] Each player picks a team; both players may pick the same team.
- [ ] Teams are snapshotted when the game leaves team selection.
- [ ] Lineup assigns each drafted champion to one roster player.
- [ ] Comfort tier is shown per pairing before confirmation.
- [ ] Opponent's lineup is hidden until both confirm.

### Simulation
- [ ] Simulation runs phases per config (lane → early → mid → late → overtime if needed) and stops when a nexus falls.
- [ ] Team style/focus and coach Synergy modifiers are applied.
- [ ] Structures (towers, inhibitors, nexus towers, nexus) are tracked per team and lane.
- [ ] All random draws use the per-game seed; a replay produces an identical result.
- [ ] Kills, gold, towers, dragons, barons, MVP, and player ranks are produced.
- [ ] Winner is the team that destroys the enemy nexus (or the timeout tiebreaker); gold never decides the winner directly.
- [ ] `simulation_version` and event log are stored with the result.
- [ ] No global mutable state (two back-to-back simulations in one process are independent).

### Results
- [ ] Winner, win condition, duration, MVP (winning team), ACE (overall), team stats, structures, lane breakdown, per-player scoreboard displayed.
- [ ] Draft (picks, bans) and comfort/matchup explanations displayed.

---

## 16. Development Phases

Same eight phases as the original spec (§41), with these adjustments:

- **Phase 1 additions:** seed-data tables and the CSV import/validation script; fix data issues in §4.
- **New Phase 1b — Team management:** teams/players/coaches CRUD, budget and validation rules, duplicate-default feature, ownership and authorization tests. Needed before team selection (Phase 2) can be completed.
- **Phase 4 (Lineup):** roster-player assignment plus comfort preview.
- **Phase 5 (Simulation):** build in this order, each with tests before moving on:
  1. Champion derived attributes + comfort + matchup (pure functions)
  2. Lane score (§9.1) with seeded RNG
  3. Lane gaps and gold diffs
  4. Objectives (dragon/baron/elder) and structures (`structures.py`: lane towers, inhibitors, nexus)
  5. Skirmish/fight, then teamfights, then sieges
  6. Phase orchestrator (lane → early → mid → late → overtime), early stop on nexus, event log
  7. Team style/focus and coach modifiers
  8. Win condition, timeout tiebreaker, MVP, ACE, ranks
  9. Persistence
- **Phase 7 (Balancing):** run the balance suite from §14; resolve the unit and formula issues in §12 *before* tuning weights.

### Suggested Build Order

```text
1. Project setup
2. Database + seed data import
3. Auth
4. Team management (CRUD + rules)
5. Lobby + settings + team selection + snapshots
6. Game state machine
7. Draft engine (incl. hidden-data filtering)
8. WebSocket sync
9. Lineup + comfort preview
10. Simulation engine (as ordered in Phase 5 above)
11. Results
12. Browser UI
13. Integration tests
14. Balancing
15. Mobile preparation
```

The critical architectural separation is unchanged: the **game engine** (draft, comfort, lane, skirmish, objectives, ranking) is pure Python with no FastAPI/DB dependency, called by the game service, exposed via the API to the web client and later a mobile client.

---

## 17. Decisions Log

The open questions from the first draft are resolved:

| # | Question | Decision | Where |
|---|---|---|---|
| 1 | Late game | **Implement** it, with overtime | §8.1 |
| 2 | Winner rule | **Nexus / towers.** Gold only determines strength at a given point in the game | §9.10, §9.11 |
| 3 | Comfort scale | **Percentages** (+40 / +25 / +10 / −10 %), not ×41 | §9.2 |
| 4 | Team style/focus and coaches | **Switched on** for V1 | §5.4, §9.6 |
| 5 | Roster content | **Users create and edit** teams, players, and coaches in a management feature; CSVs only seed defaults | §5.6 |
| 6 | Same team for both managers | **No restriction** in V1 | §5.1 |
| 7 | Hidden opponent data | **Lobby setting** `hide_player_data` set at lobby creation | §5.1, §5.3 |
| 8 | MVP | **Winning-team MVP**, plus an overall **ACE** | §9.12 |

### Follow-up decisions

| Question | Decision |
|---|---|
| Stat budget | **Soft ceiling of 32.** Custom players may exceed it; a team containing one shows a warning icon/notice to both players in the lobby ("potentially illegal team"). Never blocks play; see §5.6 |
| Champion pool | Exactly **5** champions per player; pool position sets comfort (+40 / +25 / +25 / +10 …); any champion **outside the pool** gets **−10%** (§9.2) |
| Shared/public teams | Deferred until after the initial implementation |
| Coach `Draft` stat | **Simulation only** (scales lane-matchup advantages, §5.4/§9.4); no scouting, timer, or UI effects |
| Nexus pacing | Tune with the balance suite so most games end by nexus between 25 and 35 minutes (§14) |
| Flavor fields | Player `Age` and team `Logo`/`Fanbase` have **no gameplay effect** in V1 |

### Confirmed

- Pool positions 4 and 5 both receive +10 (final pool boosts: +40, +25, +25, +10, +10; outside the pool −10%).
- The stat ceiling is soft, with an over-budget flag instead of rejection (§5.6).

No open questions remain in this spec.

---

## 18. Implementation Notes (V1 build)

What was built, and where the implementation deliberately differs from or refines the text above. The code is the source of truth for exact numbers: `backend/app/game/config.py`.

### Layout

```text
backend/app/game/        pure engine: config, models, comfort, matchup, draft_engine, lane_phase, fights,
                         objectives, structures, ranking, state, simulation_engine
backend/app/data/        CSV loader + idempotent database seeding of the default (system) content
backend/app/services/    game_service (lobby, state machine, draft, lineup, simulation), team_management_service,
                         timeouts (background draft timers), analytics (structured log events)
backend/app/api/         auth, management (teams/players/coaches/champions/config), lobbies, games
backend/app/websocket/   connection manager; /ws/games/{game_id}?token=...
backend/tests/           90 tests (engine, draft, structures, API flow, management, WebSocket)
backend/scripts/         balance.py (balance suite), smoke_test.py (full game against a running server)
backend/migrations/      Alembic (initial schema)
frontend/                React + TypeScript + Vite + React Router + TanStack Query
```

### Tuned values (from the balance suite: 1,000 seeded games, default teams, random drafts)

| Constant | Spec text | Built value | Why |
|---|---|---|---|
| `structures.siege_min_kills` | 2 | **1** | With 2, only ~65% of games ended by nexus and the median was 43 min |
| `structures.siege_base_chance` | 0.6 | **0.55** | Pacing |
| `structures.baron_extra_hits` | 2 | **3** | Pacing |
| `structures.nexus_min_minute` | (none) | **18** | New: nothing else gates the nexus, and one game ended at 13.8 min |
| `lane.scale` | (none) | **5.0** | Scales raw rolls into the lane-score range the gold model expects |
| `skill_check.scale` | (none) | **0.5** | Tempers the difficulty swing |

Result: about 98% nexus endings, median about 32 min (p10 about 24, p90 about 44), no game before 18 min, blue side about 51%, and best-pool lineups beat off-pool lineups by about +0.3 win probability. Re-run with `python -m scripts.balance 1000`.

### Refinements of the spec text

- **Skill check (9.3):** built as `uniform(min(c, c*d), max(c, c*d)) * scale`, where `c` is the comfort percentage and `d` the champion difficulty. Difficulty amplifies the comfort effect (up to d times) in either direction, so an off-pool pick on a hard champion is punished harder, and the reversed-bounds problem disappears.
- **Damage profile:** derived from `DamageType` only (`P`, `M`, `PM` = half/half). The `Style` column is loaded but has no effect on the simulation.
- **Fight resolution (9.7):** the reference formulas were uncalibrated (sturdiness dwarfed damage, `execution_diff` was almost always below 1). The port keeps the concepts (performance from lane score + gold, comfort skill check, CC/mobility/utility modifier, kill credit by performance, death credit by inverse performance, 300/150 gold) but resolves a fight by the relative strength of the two sides, so the loser only scores kills when the winner did not wipe them.
- **Phase timeline:** each phase schedules its dragons, barons, tower rolls, skirmishes and teamfights at random minutes and runs them in time order. That is what gives a real game duration when the nexus falls. CS and gold are advanced to each event's minute.
- **Late game / overtime (8.1):** as specified: 25-35 min, then up to three 5-minute overtime rounds, then the timeout tiebreaker.
- **Sieges (9.11):** hit priority is nexus, then nexus towers (once unlocked and past `nexus_min_minute`), then lane structures weighted by lane-score lead and focus lanes.
- **Data import:** `Ekko` has a blank Utility in `Champions.csv` and is loaded with 1 (reported as a warning). Champion statistics are joined by normalised name, which fixes `LeBlanc`, `Dr. Mundo`, `Nunu` and similar; 11 statistics rows for newer champions have no champion row and are ignored.

### Deviations and omissions

- **Database:** SQLite by default for development (`LDM_DATABASE_URL` selects PostgreSQL in production, with JSONB columns). `match_lane_results` and `match_player_results` are folded into `match_results.data` (JSON) rather than separate tables; `match_events` is its own table. Tables are auto-created on startup in development; `alembic upgrade head` is the production path.
- **Champion sync:** at every start the backend syncs `Champions.csv` / `ChampionStatistics.csv` into the `champions` table (`app/data/champion_sync.py`): new ids are added, differing values are updated, champions missing from the CSV are kept, the `enabled` flag is never touched, and a name clash with another id is skipped with a warning. A broken CSV is logged and the stored champions are kept so a running game is not interrupted. `python -m scripts.sync_champions [--dry-run]` does the same on demand. Default teams, players and coaches are still seeded only once.
- **No repository layer:** services query SQLAlchemy directly. Redis is not used.
- **Rate limiting:** an in-memory limiter protects the auth endpoints only.
- **Draft timeouts:** applied both by a background loop (1 s) and lazily on every request, so a game never stalls even if the loop is down.
- **Disconnects:** a WebSocket disconnect only broadcasts `PLAYER_DISCONNECTED`; it does not cancel the game. Leaving a lobby through the API does.
- **Not built:** analytics shipping (events are structured log lines), shared/public teams, mobile clients, Redis-backed scaling.

---

## 19. Importing Real Riot Accounts as Players

Users can turn a real League account into a game player. This is an optional feature: it only appears when the server has a Riot API key (`LDM_RIOT_API_KEY`).

### Approach and why

- **Riot ID lookup with a personal API key.** The user enters `GameName#TAG` and a region; the server reads the account's public ranked solo games and builds a player. Riot Sign On (OAuth) is not used: it requires an approved production key and is the right tool only for a public release, where it would also prove account ownership.
- **Imports are unverified.** Anyone can import any public Riot ID, so imported players carry a "Riot" badge and `verified: false`. A later Sign On integration can set a verified flag without changing the rest (players are linked by Riot's stable `puuid`).
- **Preview first.** `POST /riot/preview` returns a draft player plus notes; nothing is saved. The user edits it in the normal Player Editor and saves with `POST /players`, passing the `riot_ref` token from the preview. The token is signed, expires after 2 hours and is bound to the user, so the server never trusts a puuid from the browser (the puuid is never sent to the client at all).
- **Refresh.** `POST /players/{id}/riot-refresh` returns a new draft for an imported player; the user saves it to keep it.

### How a player is built (`backend/app/integrations/riot/`)

| Step | Detail |
|---|---|
| Games | Last 20 games from the **first queue that has at least 10 usable games**, tried in this order: ranked solo (420), ranked flex (440), then normal games (draft 400, blind 430, quickplay 490; ARAM and other modes are skipped). Queues are never mixed. Remakes (< 5 min) do not count. If no queue qualifies the import fails and lists the count per queue |
| Explanations | Every number in the import preview has a hover/tap tooltip. The final stat explains the fit to the 32-point ceiling (`final = round(rounded x 32 / total)`); the `(raw ...)` number lists each measurement behind it with the player's average, the role benchmark (value that scores 1 and 10) and the resulting score, plus the formula `score = 1 + 9 x (value - low) / (high - low)` (flipped when lower is better) and `raw = average of the scores`. The server sends this as `analysis.breakdown` and `analysis.fit` so the tooltip always matches what was computed |
| Source highlight | The result always states the source. Solo is shown quietly; flex or normal is highlighted in amber (import preview, player editor, player list and team cards) with a note that the stats are less reliable. The source is stored with the player (`riot_data_source`, `riot_games_used`) and comes from the signed `riot_ref` token, never from the client. Refreshing re-runs the selection, so an account that has since played enough solo games moves back to solo |
| Role | Most-played `teamPosition` (TOP, JUNGLE, MIDDLE -> MID, BOTTOM -> BOT, UTILITY -> SUPPORT); can be overridden |
| aggr | kill participation, kills per minute |
| aware | vision score per minute, dragon + baron takedowns per game |
| pos | low deaths per minute, KDA |
| dmg | damage per minute, share of team damage |
| cs | CS per minute (lane + jungle monsters) |
| Scaling | The same benchmarks are used for every queue (a simplification: normal games are usually played more loosely than ranked). Each metric is mapped to 1-10 between a low and high benchmark **for that role** (`integrations/riot/config.py`, first-guess values to be tuned on real accounts). Stats are then fitted to the soft ceiling of 32 so imports are not flagged by default; the preview shows both raw and fitted values |
| Pool | Champions by games played, topped up from champion mastery; matched to the game's champions by normalised name (so `Cho'Gath` = `Cho Gath`; `MonkeyKing` is matched through its display name Wukong). Champions the game does not have are skipped and listed; if fewer than 5 remain the user chooses the rest |

### Operating rules

- **Rate limits:** a personal key allows 20 requests/second and 100 per 2 minutes. An import costs about 23 requests, so the server paces requests with a sliding-window limiter, fails fast (HTTP 429 with a retry hint) instead of queueing, caches previews for an hour, and enforces a 10-second per-user cooldown.
- **Keys:** development keys expire every 24 hours; register a product on developer.riotgames.com for a personal key. The key lives only in the server environment.
- **Data kept:** only derived stats plus Riot ID, region and puuid. No raw match data is stored. With `hide_player_data`, the Riot link is hidden from the opponent along with the other player data.
- **Legal:** the app footer carries Riot's required "isn't endorsed by Riot Games" notice. Review Riot's Developer API Policy before any public release (section 3).

### Errors shown to users

Unknown Riot ID (404), fewer than 10 recent games in any single queue (422), bad or expired server key (503), Riot or network trouble (502), rate limited (429), unknown region/role (400).

### 19.1 Playstyle tags

Imported players can carry up to **5 playstyle tags** that nudge the simulation for that player. Hand-made and default players have none.

| | Strengths (▲ positive) | Weaknesses (▼ negative) |
|---|---|---|
| Earned from | The account's **Riot challenge levels** (`lol-challenges-v1` player-data, 1 extra request per import): the tag is earned when any of its listed challenges is at or above its minimum level (starter tags: Diamond) | The player's **averages over the imported games** (the same games and lane as the stats): a metric compared with a threshold, optionally per lane, or "never earned" in a lane |
| Starter tags | Playmaker, Duelist, Objective Hunter, Vision Controller, Farmer, Survivor, Teamfighter, Tower Breaker, Champion Ocean | Reckless, Passive, Poor Farmer, Map Blind, One Trick |

- **Suggestion and choice.** The preview lists every earned tag with why it was earned and suggests up to 5: weaknesses first, then strengths by challenge level (then percentile). In the editor the user may remove any tag, weaknesses included, and add other earned tags, but never a tag the account did not earn. The earned list travels in the signed `riot_ref` token and is stored on the player (`riot_earned_tags`); the kept keys are `playstyle_tags`. A refresh keeps the chosen tags that are still earned, or falls back to the suggestion.
- **If Riot's challenge data cannot be loaded** the import still works; only challenge tags are skipped and a note says so.
- **Effects.** A tag has one or more effects `{hook, value}`. Hooks are fixed in code (`PLAYSTYLE_HOOKS` in `game/config.py`); each has an allowed range per effect and a cap on a player's combined value:

| Hook | Applies to | Range | Cap |
|---|---|---|---|
| `lane_score` | lane-phase score × (1 + v) | ±10% | ±6% |
| `initiative` | the player's aggr when deciding who starts a fight | ±10% | ±8% |
| `objective` | the player's aware + pos in objective control | ±10% | ±6% |
| `tower` | the same, only for tower rolls | ±10% | ±6% |
| `cs_rate` | CS per minute | ±10% | ±8% |
| `fight_perf` | fight performance | ±10% | ±6% |
| `survival` | weight of being the one who dies in a fight × (1 − v) | ±15% | ±10% |
| `off_pool_penalty` | the Vulnerable comfort penalty × (1 − v) (§9.2) | ±100% | ±100% |
| `pool_best_bonus` | the Best comfort bonus × (1 + v) | ±50% | ±50% |

  Tags do not count towards the stat ceiling. A player without tags simulates exactly as before.
- **Snapshots.** A game snapshot copies each player's tags with their effects, so editing or disabling a tag later never changes a game already started. `hide_player_data` hides tags along with the other player data.
- **Admin.** Admin → Playstyle Tags lists, creates, edits and deletes tags: label, key, strength/weakness, source (challenges with a search picker over Riot's challenge list, cached for a day; or a recent-games metric with per-lane thresholds), effects, order and enabled. Deleting a tag that players keep disables it instead. The starter tags are added when the table is empty.

### 19.2 Import seal and edit detection

Before players and teams can be shared, every imported player must show whether it is a genuine Riot import and whether its strength was changed since.

- **Seal.** The preview's signed `riot_ref` token now also carries the import's **baseline**: primary role, the five stats, the imported pool champions (best first; fewer than 5 when some don't exist in the game) and the suggested tags. Saving with a `riot_ref` stores a **seal** on the player (`riot_seal`): an HS256 JWT over the Riot account (puuid, region, rank tier, source) and that baseline. It is signed with `LDM_RIOT_SEAL_KEY`, or `LDM_SECRET_KEY` when unset; keep the key stable, because changing it makes every seal unverifiable.
- **Check.** Each player view carries `riot.import_check = {status, edited_fields, original}`, recomputed on every read:

| Status | Meaning |
|---|---|
| `unedited` | The seal verifies, belongs to this account and rank, and nothing below was changed |
| `edited` | The seal verifies, but `edited_fields` lists what changed: `role`, `aggr`/`aware`/`pos`/`dmg`/`cs`, `pool`, `tags` |
| `unverified` | Linked to Riot but no valid seal: imported before seals existed, a seal that doesn't match the account or rank, or a changed key. A refresh from Riot fixes it |
| `none` | Not a Riot import (the player view's `riot` is null) |

- **Rules.** Free to change: name, age, region, secondary role, and any flavour text added later. An edit is: a different primary role or stat; changing or reordering a pool champion the import chose (filling slots it left empty is fine); dropping a suggested ▼ weakness tag (dropping a ▲ strength, or swapping earned tags, is fine). Changing a value back makes the player unedited again, and a refresh from Riot gives a new baseline.
- **Where shown.** "Riot ✓" (unedited), "Riot · edited" or "Riot · unverified" badges on the player list, team cards and the draft player panel, with details on hover. The editor shows each changed field's imported value and warns before saving an edit. `riot.verified` still means account *ownership* (always false until Riot Sign On).
- **Games and hidden data.** Snapshots copy the check as it was at draft start. `hide_player_data` hides it along with the rest of `riot`.
- **Sharing (future).** The seal binds the account and values, not the player row: a shared copy stays verifiable as long as `riot_seal` and the `riot_*` columns are copied with it.

---

## 20. Single Player Mode

A user can simulate games alone. The "Create a lobby" card on the home page has two tabs, **Single Player** and **Multiplayer**.

- **What it is:** a sandbox. One user holds both seats, chooses a team for Blue and for Red (from their own teams plus the defaults; the same team on both sides is allowed), makes **every pick and ban for both sides**, assigns and confirms both lineups, and sees the simulated match. There is no computer opponent.
- **Data:** `games.is_solo`; both `blue_player_id` and `red_player_id` are the same user. The lobby is created already in `TEAM_SELECTION` (nobody needs to join). `hide_player_data` is forced off. Bans on/off, timers on/off and the pick/ban seconds work as in multiplayer; the Single Player tab defaults to timers off.
- **Acting side:** in multiplayer the server derives the side from the caller; with one caller on both seats it cannot, so single player is explicit: `POST /lobbies/{id}/team` and `PUT /games/{id}/lineup` take `side`, `POST /games/{id}/lineup/ready` and `GET /games/{id}/lineup/preview` take a `?side=` query, and draft picks/bans act for whichever team the draft says is up (the usual wrong-type, duplicate-champion and turn-order checks still run). `POST /games/{id}/ready` starts the draft once both teams are chosen. A missing side is a 400.
- **Not available in single player:** joining (409), swapping sides (409), hidden player data.
- **State:** `settings.mode` is `SOLO` or `MULTI`; in solo the `lineup` block carries both `blue` and `red`. Everything after the draft (snapshots, simulation, seed, version, results, events) is the multiplayer code path, so results are identical in kind and stored the same way.
- **UI:** a purple/gold banner says "Single player: you control both sides" (plus which side is up during the draft); the draft's green turn glow and pool hints follow the side currently picking; the lineup screen shows the Blue and Red editors one after the other, each with its own Confirm; the result shows "Match result" instead of Victory/Defeat.

---

## 21. Seasons

A **season** is a league or tournament: a user creates it with the usual lobby rules, enters a team, and manages that team through every round while the CPU builds and runs every other team. It is built in phases: phase 1 is a single player, Bring Your Own league; phase 2 adds Swiss stages and playoff brackets; phase 3 lets friends manage teams in the same season.

- **Setup.** `POST /seasons {name, roster_mode, format, rules, options}`. `rules` are the lobby options (ruleset, draft options and team restrictions); their series format is ignored, because the season sets match length (`options.regular_series`, BO1/BO3/BO5) and Fearless only applies to best of 3 and 5 fixtures. `options`: `team_count` (4–16), `human_slots` (1 to `team_count`: teams users can manage), `rr_double`, `regular_series`, `cpu_strength` (WEAKER / EVEN / STRONGER), `round_deadline_hours` (0–336, 0: none). A user can have at most 10 unfinished seasons. `roster_mode: DRAFT` is refused (400) until phase 4.
- **Frozen copies.** `POST /seasons/{id}/teams {team_id}` checks the team is complete and meets the season's team restrictions, then copies the team, its players and coach into the season (`season_id` set on the copies). Season copies never appear on the management pages, don't count toward per-user limits, can't be edited, shared or copied, and later edits to the original don't reach the season. Withdraw with `DELETE /seasons/{id}/teams/mine` before the start.
- **CPU teams.** `POST /seasons/{id}/start` (creator only) generates the missing teams (`game/player_generator.py`): five players with role-weighted stats and five-champion pools from each lane's usual champions, a coach, a name, logo, styles and focus lanes. Each player's total stays within the rules' player cap (else the max rank's budget, else 36) times the strength share (80 / 90 / 98%), and the five fit the team cap. CPU players are not Riot imports, so a max rank restriction only applies to managers' teams. Teams are then seeded at random and the whole round robin is drawn (`game/competition.py`, circle method: an odd count gives each team one bye; double round robin repeats it with home and away swapped). The home team is Blue in game 1.
- **Fixtures.** Each `SeasonMatch` is a best-of series; every game is an ordinary `Game` with `season_match_id`, so drafts, results, replays and series work unchanged. A manager either plays live (`POST /seasons/matches/{id}/play`: the game opens straight in the draft against the CPU, and pressing it again returns the game in progress) or auto-sims (`POST /seasons/matches/{id}/auto`: the CPU drafts and sets lineups for both sides, `game_service.autoplay_game`, finishing a live game part way through if needed). In an auto-played series the loser takes Blue next game. Season games never expire, can't be left, re-run or rematched, and their teams and sides are fixed.
- **Rounds.** `POST /seasons/{id}/advance {force}` (creator only) closes the current round: every CPU vs CPU fixture is auto-played then. A manager's unplayed fixture blocks it (409) unless `force`, which auto-sims it. After the last round robin round it moves on to the playoffs (or ends with the top of the table as champion); a Swiss round is followed by the next Swiss round until every team is decided, then the bracket; the last playoff round ends the season.
- **Formats.** `format: ROUND_ROBIN` plays the whole round robin, then (with `options.playoff_size` 2, 4 or 8, at most the team count) the top of the table goes into single-elimination playoffs; with no playoffs the top of the table is champion. `format: SWISS` needs 8 or 16 teams: each round pairs teams with the same record (round 1: top half of the seeds against the bottom half; later rounds avoid rematches within a record group when possible, and the team with fewer home matches is home). 2 wins qualifies and 2 losses eliminates with 8 teams, 3 and 3 with 16, so half the field qualifies within at most 3 or 5 rounds. The qualifiers are seeded by fewest losses, then game difference, then seed. Swiss rounds are drawn one at a time as the previous one closes.
- **Playoffs.** Standard bracket seeding (1 v 8, 4 v 5, 2 v 7, 3 v 6, the better seed at home), so the top two seeds can only meet in the final. Each round is drawn when the previous one closes; the winner of the upper match of each pair is home. `playoff_series` sets the match length for every round but the final, which uses `final_series`. The final's winner is champion. `SeasonTeam.eliminated` marks teams that missed the playoffs, went out in the Swiss stage or were knocked out.
- **Standings.** Match wins, then head-to-head wins among the tied teams, then game differential, then game wins, then seed. Each row also has the current streak and last five results.
- **Watching.** The creator and every manager are season members: they can open any of the season's games, results and series (read only), and nobody else can see the season (404).
- **Views.** `GET /seasons` (yours), `GET /seasons/{id}` (hub: settings, teams with ratings, standings, this round's matches, your match), `GET /seasons/{id}/schedule`, `GET /seasons/{id}/teams/{season_team_id}` (roster, record, fixtures and per-player season totals: games, K/D/A, CS, gold, damage, MVPs; hidden for other teams while `hide_player_data` is on). `POST /seasons/{id}/cancel` ends a season early.
- **UI.** A Seasons tab in the top bar and a card on the home page; `/seasons` (list), `/seasons/new` (four-step form), `/seasons/{id}` (Overview, Standings, Schedule, Teams), `/seasons/{id}/teams/{teamId}`. Season games show a strip linking back to the season.
- **Views (phase 2).** The hub carries `stage` (REGULAR / SWISS / PLAYOFF, null when not in play), `stage_label`, `total_rounds` for the current stage, `bracket` (every round with its name, match length, slots and the matches drawn so far) and per standings row `swiss_status` and `eliminated`; the schedule groups rounds by stage. The UI adds a format picker, playoff options and a Bracket tab.
- **Multiplayer (phase 3).**
  - *Joining.* `GET /seasons/join/{code}` previews a season by its 6-character code (no membership needed: rules, options, managers, open slots, `can_join`); `POST /seasons/join/{code} {team_id}` enters a team with the same checks as `POST /seasons/{id}/teams`. Joining is only possible during setup and while `managers < human_slots`. Two teams with the same name can't be in one season (409). The creator doesn't need a team of their own; the season can start once any manager has entered one.
  - *Manager vs manager fixtures.* `play` opens a multiplayer game (both seats set, `vs_cpu` off, `hide_player_data` from the rules) at the ready check with the caller ready; the other manager's `play` (or `POST /games/{id}/ready`) starts the draft. Everything after is the normal multiplayer flow, including draft timers and series. Against the CPU player data is never hidden.
  - *Mutual auto-sim.* Between two managers `POST /seasons/matches/{id}/auto {ready}` records a request (`auto_requested.home/away` on the match); the CPU plays the match only once both have asked. `ready: false` takes a request back. Against the CPU it plays straight away as before.
  - *Leaving.* `POST /seasons/{id}/teams/{season_team_id}/release`: a manager leaves their own team, or the creator removes anyone's. Before the start the entry is withdrawn; after it the CPU manages the team for the rest of the season (`game_service.cpu_takes_over`: the seat empties, the game turns vs CPU and carries on from its current state: ready check, draft turn, lineup or between series games). A manager who left is no longer a member. The creator keeps running the season after handing their own team to the CPU.
  - *Round deadlines.* With `round_deadline_hours` each round gets `round_deadline_at` when it opens. The background loop (`timeouts.process_due_games` → `season_service.process_deadlines`) force-advances a season once its deadline passes; if a manager is mid-game right then it waits up to 30 minutes for that game first. The creator can still advance sooner.
  - *Live updates.* `/ws/seasons/{id}?token=` (members only, else closed with 4403) sends `SEASON_UPDATED` whenever the season changes: joins, starts, results (including other managers' games), rounds, deadlines, managers leaving. Clients refetch the hub; polling drops to once a minute as a safety net. Game channels are unchanged.
  - *UI.* The create page picks the number of managers and the round deadline. Setup shows the invite code and link and a Managers card (withdraw, remove). `/seasons` has a Join-by-code box, `/seasons/join/{code}` previews and joins. The match card handles the ready check and the auto-sim agreement; season games between managers have their own ready screen (no team picker, Leave or side swap). The header shows the time left in the round.
- **Planned phases.** 4: Player Draft mode (the creator fills a pool, managers snake-draft rosters) and a free agency pool. Later: season stat leaders and awards, notifications, format templates (LCS / MSI / Worlds style), and player progression, which §2 lists as a V1 non-goal.
