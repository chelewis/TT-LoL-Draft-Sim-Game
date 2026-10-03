# League Simulator — Game Specification

## 1. Overview

**League Simulator** is a browser-based multiplayer game inspired by the team composition and drafting aspects of League of Legends.

Two users join a private lobby, complete a pick/ban draft, assign their selected champions to lanes/players, confirm their lineups, and start a simulated match. The backend then calculates the result of the simulated match and presents both players with a match summary.

### Initial Platform

- **Version 1:** Responsive web application
- **Future:** iOS and Android mobile applications
- **Backend:** Python REST API
- **Frontend:** Web application
- **Database:** PostgreSQL recommended
- **Authentication:** Token-based authentication
- **Real-time:** WebSocket support recommended for lobby/draft state updates

### Core Game Loop

```text
Login
  ↓
Create / Join Lobby
  ↓
Both Players Ready
  ↓
Pick / Ban Phase
  ↓
Assign Champions to Lanes
  ↓
Both Players Confirm
  ↓
Simulate Match
  ↓
Calculate Winner
  ↓
Display Match Results
```

---

# 2. Product Goals

## Primary Goals

1. Allow two users to compete in a simulated League-style match.
2. Make the pick/ban phase the primary strategic gameplay mechanic.
3. Keep matches short and easy to understand.
4. Make the simulation deterministic enough to feel logical while retaining some randomness.
5. Separate game rules and simulation logic from the web frontend.
6. Design the backend so a future mobile application can use the same API.

## Non-Goals for Version 1

The first version should **not** attempt to reproduce the full League of Legends game.

Do not initially implement:

- Real-time champion movement
- Summoner control
- Minion simulation
- Item purchasing during a match
- Detailed combat animation
- Map rendering
- Full League client functionality
- Voice chat
- Spectator mode
- Ranked matchmaking
- Complex progression systems
- Riot account integration
- Live League of Legends game data integration

The game should instead simulate the strategic outcome of a drafted team.

---

# 3. Important IP / Data Consideration

The game is inspired by League of Legends but should be architected so that its core simulation engine is independent of League-specific data.

If League of Legends champions, names, artwork, descriptions, statistics, or other Riot Games assets are used, the project must comply with applicable Riot Games intellectual-property and developer policies.

The application should therefore maintain a generic internal concept of a `Champion`, while allowing the data layer to contain the specific champion data used by the game.

Example:

```text
Champion
├── id
├── name
├── roles
├── stats
├── abilities
├── synergies
├── counters
└── metadata
```

The simulation engine should operate on these properties rather than hard-coding individual champions throughout the application.

---

# 4. Users

Version 1 supports two players per game.

## Player

A player can:

- Create a lobby
- Join a lobby
- Invite another player through a lobby code
- Enter a draft
- Pick champions
- Ban champions
- Assign champions to lanes
- Confirm their lineup
- View the simulated match
- View match results
- Leave a lobby

---

# 5. Game Structure

Each game consists of:

1. Lobby
2. Draft
3. Team Assignment
4. Ready Check
5. Simulation
6. Results

## Game States

The backend should maintain an explicit state machine.

```text
WAITING_FOR_PLAYERS
        ↓
READY_CHECK
        ↓
DRAFTING
        ↓
LANE_ASSIGNMENT
        ↓
READY_TO_SIMULATE
        ↓
SIMULATING
        ↓
COMPLETED
```

A game may also enter:

```text
CANCELLED
```

if a player leaves or the lobby expires.

The backend must be authoritative over state transitions.

---

# 6. Lobby

## Create Lobby

A user can create a new lobby.

The server generates a unique lobby code.

Example:

```text
GP7K42
```

The lobby initially contains:

```json
{
  "status": "WAITING_FOR_PLAYERS",
  "players": [
    {
      "id": "user-123",
      "team": "BLUE"
    }
  ]
}
```

## Join Lobby

A second player enters the lobby code.

Once two players are present:

```text
Player 1 → Blue Team
Player 2 → Red Team
```

The server should reject a third player.

## Lobby Expiration

Unused lobbies should expire after a configurable period.

Suggested default:

```text
30 minutes
```

Completed games should remain available long enough for players to view their results.

---

# 7. Draft System

The draft is the primary gameplay mechanic.

The initial implementation should use a predefined draft sequence.

## Draft Requirements

The system must support:

- Champion bans
- Champion picks
- Turn order
- Draft timers
- Validation
- Draft completion
- Disconnect/reconnect handling

## Example Draft

Version 1 can use a simplified sequence:

```text
Blue Ban
Red Ban
Blue Ban
Red Ban
Blue Ban
Red Ban

Blue Pick
Red Pick
Red Pick
Blue Pick
Blue Pick
Red Pick

Red Ban
Blue Ban

Red Pick
Blue Pick
Blue Pick
Red Pick

```

This produces:

```text
Blue Team: 5 champions
Red Team: 5 champions
```

The exact sequence should be stored in configuration rather than hard-coded into frontend code.

Example:

```json
{
  "draft_type": "STANDARD",
  "actions": [
    "BLUE_BAN",
    "RED_BAN",
    "BLUE_BAN",
    "RED_BAN",
    "BLUE_PICK",
    "RED_PICK",
    "RED_PICK",
    "BLUE_PICK",
    "BLUE_PICK",
    "RED_PICK",
    "BLUE_BAN",
    "RED_BAN",
    "RED_PICK",
    "BLUE_PICK"
  ]
}
```

The draft engine should support changing this sequence later.

---

# 8. Champion Selection Rules

A champion can only be selected if:

```text
Champion is available
AND
Champion has not already been picked
AND
Champion has not already been banned
```

Once selected, a champion becomes unavailable to both players.

The backend must validate every selection.

The frontend should never be trusted to enforce game rules.

---

# 9. Draft Timer

Each draft action should have a countdown.

Suggested initial value:

```text
30 seconds
```

The timer should be controlled by the backend.

The frontend receives:

```json
{
  "action": "BLUE_PICK",
  "started_at": "2026-09-30T15:00:00Z",
  "expires_at": "2026-09-30T15:00:30Z"
}
```

The frontend calculates/display the remaining time.

## Timeout Behavior

If a player does not act before the timer expires, the server automatically selects a legal action.

Version 1 behavior:

- For bans: select a random available champion
- For picks: select a random available champion

This prevents games from becoming permanently stuck.

Later versions may implement smarter automatic selection.

---

# 10. Lane Assignment

After the draft, each team has five champions.

Players assign champions to:

```text
TOP
JUNGLE
MID
ADC
SUPPORT
```

Each lane can contain exactly one champion.

Example:

```text
Blue Team

TOP       → Champion A
JUNGLE    → Champion B
MID       → Champion C
ADC       → Champion D
SUPPORT   → Champion E
```

The assignment phase should support drag-and-drop on desktop and tap/select interactions on mobile.

The backend should store lane assignments independently from the UI.

---

# 11. Ready System

Both players must confirm their lineups.

Example:

```text
Blue Team: READY
Red Team: NOT READY
```

The match cannot start until:

```text
Blue Team = READY
AND
Red Team = READY
```

When both players are ready:

```text
LANE_ASSIGNMENT
        ↓
READY_TO_SIMULATE
        ↓
SIMULATING
```

---

# 12. Match Simulation

The simulation engine is the core backend game system.

The simulation should not depend on the browser.

It should be implemented as a standalone Python module/service.

Example:

```text
backend/
├── game/
│   ├── draft.py
│   ├── team.py
│   ├── simulation.py
│   ├── scoring.py
│   └── results.py
```

The simulation receives two completed teams:

```python
result = simulate_match(
    blue_team=blue_team,
    red_team=red_team,
    seed=game_seed
)
```

It returns a structured result.

---

# 13. Simulation Model

Version 1 should use a scoring model rather than attempting to recreate actual League combat.

Each champion should have attributes relevant to simulation.

Example:

```json
{
  "id": "champion-001",
  "name": "Example Champion",
  "roles": ["MID"],
  "stats": {
    "early_game": 78,
    "scaling": 91,
    "team_fight": 84,
    "objective_control": 65,
    "lane_strength": 88,
    "utility": 72
  }
}
```

The actual stats and formulas should be maintained in data/configuration rather than embedded throughout application code.

---

# 14. Team Strength

The simulation can calculate a team score from several components.

Example:

```text
Team Score =
    Champion Strength
  + Lane Strength
  + Team Synergy
  + Objective Strength
  + Team Fight Strength
  + Scaling
  + Draft Advantages
  + Random Variance
```

Each component should have a configurable weight.

Example:

```python
SIMULATION_WEIGHTS = {
    "lane_strength": 0.20,
    "team_synergy": 0.20,
    "team_fighting": 0.20,
    "objective_control": 0.15,
    "scaling": 0.15,
    "draft_advantage": 0.10
}
```

These values are examples only and should be easy to tune.

---

# 15. Lane Simulation

Each lane produces a score.

Example:

```text
Top
Blue: 82
Red: 76

Jungle
Blue: 71
Red: 84

Mid
Blue: 91
Red: 78

ADC
Blue: 85
Red: 86

Support
Blue: 79
Red: 81
```

Lane scores contribute to the overall team result.

The simulation should account for:

- Champion lane strength
- Champion role suitability
- Champion matchup
- Synergy
- Random variance

---

# 16. Champion Matchups

The game should eventually support matchup relationships.

Example:

```json
{
  "champion_a": "champion-001",
  "champion_b": "champion-002",
  "advantage": 8
}
```

Positive value:

```text
Champion A has an advantage.
```

Negative value:

```text
Champion B has an advantage.
```

The matchup system should not be hard-coded into the simulation engine.

---

# 17. Team Synergy

The simulation should reward compatible team compositions.

Possible synergy categories:

```text
ENGAGE
POKE
TEAM_FIGHT
PROTECT
SPLIT_PUSH
SCALING
EARLY_GAME
OBJECTIVE_CONTROL
```

A team may have multiple composition traits.

Example:

```json
{
  "composition": {
    "engage": 84,
    "poke": 62,
    "team_fight": 91,
    "scaling": 78
  }
}
```

The game can compare composition strengths between teams.

---

# 18. Randomness

The game should contain controlled randomness so that the stronger draft does not win every time.

Example:

```python
variance = random.uniform(-10, 10)
final_score = calculated_score + variance
```

The exact formula should be configurable.

Every match should receive a unique random seed.

Store the seed with the match:

```text
game.seed
```

This allows the result to be reproduced for debugging.

---

# 19. Match Result

The result should include:

```json
{
  "winner": "BLUE",
  "blue_score": 82.4,
  "red_score": 76.8,
  "duration_seconds": 1840,
  "lanes": {
    "TOP": {
      "blue_score": 82,
      "red_score": 76
    },
    "JUNGLE": {
      "blue_score": 71,
      "red_score": 84
    }
  }
}
```

The frontend should present the result in an understandable way.

---

# 20. Match Summary

The result screen should display:

## Winner

```text
BLUE TEAM WINS
```

## Team Scores

```text
Blue: 82.4
Red: 76.8
```

## Lane Results

```text
TOP       Blue advantage
JUNGLE    Red advantage
MID       Blue advantage
ADC       Even
SUPPORT   Red advantage
```

## Draft Summary

Show:

- Picks
- Bans
- Lane assignments
- Team composition
- Key advantages

The result should explain the outcome without exposing internal implementation details.

Example:

```text
Blue Team gained an advantage from stronger mid-lane performance
and higher team-fight synergy.
```

---

# 21. Backend Architecture

Recommended Python stack:

```text
Python
FastAPI
SQLAlchemy
PostgreSQL
Pydantic
Alembic
Redis (optional initially)
WebSockets
Pytest
```

## Recommended Architecture

```text
                    Web Browser
                         |
                         |
                    HTTPS / WSS
                         |
                         ↓
                  FastAPI Backend
                         |
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
       API Layer      Game Engine     WebSockets
          |              |
          ↓              ↓
      Services       Simulation
          |
          ↓
      Repository
          |
          ↓
      PostgreSQL
```

---

# 22. Backend Project Structure

Recommended structure:

```text
backend/
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── lobbies.py
│   │   ├── games.py
│   │   └── champions.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   └── dependencies.py
│   │
│   ├── models/
│   │   ├── user.py
│   │   ├── lobby.py
│   │   ├── game.py
│   │   ├── champion.py
│   │   ├── draft.py
│   │   └── result.py
│   │
│   ├── schemas/
│   │   ├── user.py
│   │   ├── lobby.py
│   │   ├── game.py
│   │   ├── draft.py
│   │   └── result.py
│   │
│   ├── services/
│   │   ├── lobby_service.py
│   │   ├── draft_service.py
│   │   ├── game_service.py
│   │   └── champion_service.py
│   │
│   ├── game/
│   │   ├── draft_engine.py
│   │   ├── simulation_engine.py
│   │   ├── scoring.py
│   │   ├── matchup.py
│   │   └── composition.py
│   │
│   ├── repositories/
│   │   ├── lobby_repository.py
│   │   ├── game_repository.py
│   │   └── champion_repository.py
│   │
│   └── websocket/
│       └── manager.py
│
├── migrations/
├── tests/
├── requirements.txt
├── alembic.ini
└── README.md
```

The game engine should remain independent of FastAPI wherever practical.

---

# 23. API Design

All API endpoints should be versioned.

Base URL:

```text
/api/v1
```

## Authentication

```http
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

## Lobby

```http
POST /api/v1/lobbies
POST /api/v1/lobbies/{lobby_code}/join
GET  /api/v1/lobbies/{lobby_id}
POST /api/v1/lobbies/{lobby_id}/leave
```

## Game

```http
GET  /api/v1/games/{game_id}
POST /api/v1/games/{game_id}/ready
GET  /api/v1/games/{game_id}/state
```

## Draft

```http
GET  /api/v1/games/{game_id}/draft
POST /api/v1/games/{game_id}/draft/pick
POST /api/v1/games/{game_id}/draft/ban
```

## Lane Assignment

```http
PUT /api/v1/games/{game_id}/lineup
POST /api/v1/games/{game_id}/lineup/ready
```

## Results

```http
GET /api/v1/games/{game_id}/result
```

---

# 24. API Rules

The API must enforce:

- Authentication
- Player ownership
- Game state
- Draft turn
- Draft timer
- Champion availability
- Team assignment
- Lane uniqueness
- Ready status
- Game completion
- Valid state transitions

Example:

A player must not be able to call:

```http
POST /draft/pick
```

when it is the opponent's turn.

The server must reject the request even if the frontend accidentally allows the action.

---

# 25. WebSocket

WebSockets should be used for real-time game state updates.

Example endpoint:

```text
/ws/games/{game_id}
```

Events may include:

```text
PLAYER_JOINED
PLAYER_READY
DRAFT_STARTED
DRAFT_ACTION_STARTED
CHAMPION_PICKED
CHAMPION_BANNED
DRAFT_COMPLETED
LINEUP_UPDATED
PLAYER_READY
SIMULATION_STARTED
SIMULATION_COMPLETED
PLAYER_DISCONNECTED
PLAYER_RECONNECTED
GAME_CANCELLED
```

Example event:

```json
{
  "type": "CHAMPION_PICKED",
  "game_id": "game-123",
  "team": "BLUE",
  "champion_id": "champion-001",
  "draft_action": 5
}
```

The WebSocket is for notifying clients.

The REST API remains authoritative for mutations.

---

# 26. Database Model

Recommended initial entities:

```text
users
lobbies
games
game_players
champions
draft_actions
team_lineups
match_results
match_lane_results
```

## Users

```text
id
username
email
password_hash
created_at
updated_at
```

## Lobbies

```text
id
code
status
created_by
created_at
expires_at
```

## Games

```text
id
lobby_id
status
blue_player_id
red_player_id
draft_phase
current_action
seed
started_at
completed_at
created_at
```

## Champions

```text
id
name
enabled
roles
stats
metadata
created_at
updated_at
```

JSON/JSONB may be used for flexible champion attributes.

## Draft Actions

```text
id
game_id
action_number
team
action_type
champion_id
started_at
completed_at
```

## Team Lineups

```text
id
game_id
team
lane
champion_id
```

## Match Results

```text
id
game_id
winner
blue_score
red_score
duration_seconds
seed
created_at
```

---

# 27. Data Integrity

The database should enforce appropriate constraints.

Examples:

```text
One game has exactly two players.
A team cannot have two champions assigned to the same lane.
A champion cannot appear twice in the same game.
A draft action belongs to exactly one game.
A completed game has exactly one result.
```

Where possible, use database constraints in addition to application-level validation.

---

# 28. Frontend

The browser frontend should be a responsive single-page application.

A suitable initial stack:

```text
React
TypeScript
Vite
React Router
TanStack Query
WebSocket client
```

The exact frontend framework can change, but the application should remain API-first.

## Primary Screens

```text
Login
Home
Create Lobby
Join Lobby
Lobby
Draft
Lane Assignment
Match Simulation
Match Results
Profile / Settings
```

---

# 29. Mobile-First UI Considerations

Even though Version 1 is browser-first, all UI components should be responsive.

Avoid designs that require desktop-only interactions.

Every desktop interaction should have a mobile equivalent.

Examples:

### Desktop

```text
Drag champion → lane
```

### Mobile

```text
Tap champion
↓
Select lane
```

The API must not depend on either interaction style.

---

# 30. Future Mobile Application

The eventual mobile app should communicate with the same backend.

```text
             ┌──────────────┐
             │ Python API   │
             └──────┬───────┘
                    │
          ┌─────────┴─────────┐
          ↓                   ↓
    Web Application      Mobile App
```

Do not create separate game logic for mobile.

The simulation engine remains server-side.

The mobile app becomes another client of the same API.

Potential future mobile technology:

```text
React Native
Flutter
```

Either can consume the same REST/WebSocket API.

---

# 31. State Synchronization

The server should be authoritative.

Clients should maintain a local representation of game state but should not determine official state.

Example:

```text
Client:
"Player selected Champion A"

Server:
"Validate selection"

Server:
"Save selection"

Server:
"Broadcast CHAMPION_PICKED"

Clients:
"Update UI"
```

Never rely on the frontend to determine whether an action is legal.

---

# 32. Reconnection

Players should be able to refresh the browser without losing the game.

When reconnecting:

```http
GET /api/v1/games/{game_id}/state
```

The server returns the complete current state.

The client then reconnects to the WebSocket.

This is especially important for mobile development.

---

# 33. Game State Response

The API should provide a complete state representation.

Example:

```json
{
  "game_id": "game-123",
  "status": "DRAFTING",
  "players": {
    "blue": {
      "id": "user-1",
      "ready": false
    },
    "red": {
      "id": "user-2",
      "ready": false
    }
  },
  "draft": {
    "current_action": 5,
    "current_team": "BLUE",
    "action_type": "PICK",
    "expires_at": "2026-09-30T15:10:30Z",
    "bans": [],
    "blue_picks": [],
    "red_picks": []
  }
}
```

A full state endpoint makes reconnection and mobile development significantly easier.

---

# 34. Security

The backend must assume the client is untrusted.

Implement:

- Password hashing
- Secure authentication tokens
- Authorization checks
- Rate limiting
- Input validation
- Server-side game validation
- WebSocket authorization
- CORS configuration
- HTTPS in production
- Secrets stored in environment variables
- Database credentials outside source control

Never expose private database credentials to the frontend.

---

# 35. Anti-Cheat

Because the simulation happens on the server, players should not be able to manipulate match results through the browser.

The following must happen server-side:

```text
Draft validation
Champion availability
Lane validation
Ready validation
Random seed generation
Simulation
Winner calculation
Result persistence
```

The frontend should only request actions.

---

# 36. Observability

The backend should log:

```text
Lobby creation
Lobby join
Draft actions
Invalid actions
Player disconnects
Simulation start
Simulation completion
Errors
```

Every game should have a unique `game_id`.

Simulation logs should include:

```text
game_id
seed
team scores
winner
simulation version
```

Example:

```text
game_id=abc123
simulation_version=1.0
seed=4928191
winner=BLUE
```

This makes balancing and debugging easier.

---

# 37. Simulation Versioning

Simulation formulas will change frequently during development.

Store a simulation version with every result.

Example:

```text
simulation_version = "1.0.0"
```

If the formula changes:

```text
1.0.0 → 1.1.0
```

Historical games retain their original version.

This is important for debugging and analytics.

---

# 38. Analytics

Track basic gameplay events from the beginning.

Examples:

```text
lobby_created
lobby_joined
draft_started
champion_picked
champion_banned
draft_completed
lineup_confirmed
simulation_started
game_completed
player_disconnected
```

Do not make analytics a prerequisite for gameplay, but structure events so they can later be sent to an analytics system.

---

# 39. Testing Strategy

## Unit Tests

Test:

- Draft sequence
- Champion validation
- Ban validation
- Pick validation
- Lane assignment
- Team scoring
- Matchups
- Synergy
- Random variance
- Winner calculation
- State transitions

## Integration Tests

Test:

```text
Create lobby
→ Join lobby
→ Start draft
→ Complete draft
→ Assign lanes
→ Ready both players
→ Simulate game
→ Retrieve result
```

## API Tests

Verify:

- Authentication
- Authorization
- Invalid game states
- Invalid draft actions
- Duplicate selections
- Unauthorized game access
- Reconnection

## Frontend Tests

Test:

- Lobby flow
- Draft UI
- Timer
- Champion selection
- Lane assignment
- Ready state
- Results

---

# 40. MVP Acceptance Criteria

Version 1 is complete when:

### Lobby

- [ ] User can create a lobby.
- [ ] User can join using a code.
- [ ] Exactly two players can join.
- [ ] Both players can see lobby state.
- [ ] Players can reconnect.

### Draft

- [ ] Draft begins once both players are ready.
- [ ] Draft follows configured action order.
- [ ] Only the active player can act.
- [ ] Players can ban champions.
- [ ] Players can pick champions.
- [ ] Duplicate picks are prevented.
- [ ] Banned champions cannot be picked.
- [ ] Draft timer works.
- [ ] Timeout produces an automatic legal action.
- [ ] Draft completion is detected.

### Lineup

- [ ] Each player has five champions.
- [ ] Champions can be assigned to five lanes.
- [ ] Each lane can only contain one champion.
- [ ] Both players can confirm their lineup.

### Simulation

- [ ] Server simulates the match.
- [ ] A seed is generated.
- [ ] Team scores are calculated.
- [ ] Winner is determined.
- [ ] Match result is persisted.
- [ ] Simulation version is stored.

### Results

- [ ] Winner is displayed.
- [ ] Team scores are displayed.
- [ ] Lane results are displayed.
- [ ] Draft information is displayed.
- [ ] Both players can view the result.

### Architecture

- [ ] Game logic is independent of frontend.
- [ ] API is versioned.
- [ ] WebSocket updates work.
- [ ] Browser refresh does not destroy the game.
- [ ] API can support a future mobile client.

---

# 41. Recommended Development Phases

## Phase 1 — Backend Foundation

Build:

- FastAPI application
- PostgreSQL connection
- SQLAlchemy models
- Alembic migrations
- Authentication
- API structure
- Basic testing

## Phase 2 — Lobby

Build:

- Create lobby
- Join lobby
- Lobby code
- Player assignment
- Lobby state
- WebSocket connection
- Reconnection

## Phase 3 — Draft Engine

Build:

- Draft state machine
- Draft configuration
- Pick/ban validation
- Draft timer
- Automatic timeout action
- WebSocket events

This should be implemented and tested independently from the frontend.

## Phase 4 — Lineup

Build:

- Five lanes
- Champion assignment
- Assignment validation
- Ready system

## Phase 5 — Simulation Engine

Build:

- Champion statistics
- Lane scoring
- Matchups
- Team composition
- Synergy
- Random variance
- Winner calculation
- Result persistence

## Phase 6 — Web Frontend

Build:

- Authentication
- Lobby UI
- Draft UI
- Lane assignment
- Ready screen
- Simulation screen
- Results screen

## Phase 7 — Testing & Balancing

Test complete matches and tune simulation weights.

Focus on:

```text
Is the simulation understandable?
Does drafting matter?
Does randomness matter without overwhelming strategy?
Are results believable?
```

## Phase 8 — Mobile Preparation

Before mobile development:

- Stabilize API contracts
- Document WebSocket events
- Ensure all game state can be retrieved through API
- Ensure responsive UI
- Remove browser-specific assumptions from game logic
- Establish API authentication suitable for mobile clients

---

# 42. Configuration

Game rules should be configurable.

Example:

```python
GAME_CONFIG = {
    "draft_timer_seconds": 30,
    "lobby_expiration_minutes": 30,
    "lanes": [
        "TOP",
        "JUNGLE",
        "MID",
        "ADC",
        "SUPPORT"
    ],
    "simulation": {
        "random_variance": 10,
        "version": "1.0.0"
    }
}
```

Avoid hard-coding these values across multiple files.

---

# 43. Future Features

Potential future features should not be required for MVP but the architecture should not prevent them.

## Multiplayer

- More than two users
- Private rooms
- Matchmaking
- Ranked games

## Game Modes

- Standard
- Random draft
- Blind draft
- Tournament
- Custom rules

## Progression

- Player XP
- Levels
- Statistics
- Win/loss records
- Achievements

## Competitive

- Ranked ladder
- ELO/MMR
- Seasons
- Leaderboards
- Tournaments

## Social

- Friends
- Profiles
- Chat
- Spectating
- Rematches

## Monetization

Potential future models:

- Premium cosmetics
- Premium game modes
- Advanced statistics
- Custom tournaments
- Subscription
- Battle passes

These should not influence the core game architecture.

---

# 44. Development Principles

The development team/coding agent should follow these principles:

### 1. Backend is authoritative

Never trust the client for game rules or results.

### 2. Game engine is independent

The simulation and draft engines should be usable without FastAPI.

### 3. API-first

Every important game operation should have a clean API representation.

### 4. Mobile-ready

Do not introduce web-specific assumptions into core game logic.

### 5. Deterministic debugging

Store the simulation seed and simulation version.

### 6. Configurable rules

Draft sequences, timers, simulation weights, and game settings should be configurable.

### 7. Small MVP

Do not build features that are not required to complete the core game loop.

### 8. Test the game engine heavily

The draft and simulation engines should have extensive automated tests.

---

# 45. Initial Build Priority

The recommended implementation order is:

```text
1. Project setup
2. Database
3. Authentication
4. Lobby
5. Game state machine
6. Draft engine
7. WebSocket synchronization
8. Lane assignment
9. Ready system
10. Simulation engine
11. Results
12. Browser UI
13. Integration testing
14. Simulation balancing
15. Mobile preparation
```

The most important architectural separation is:

```text
             GAME ENGINE
        ┌───────────────────┐
        │ Draft Engine      │
        │ Simulation Engine │
        │ Scoring           │
        │ Matchups          │
        │ Composition       │
        └─────────┬─────────┘
                  │
                  ↓
             GAME SERVICE
                  │
                  ↓
              FASTAPI
                  │
        ┌─────────┴─────────┐
        ↓                   ↓
   Web Browser          Future Mobile
```

This allows the same game to be played through the browser today and through a native mobile client later without rebuilding the underlying game.
