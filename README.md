# League Draft Manager

A two-player, browser-based drafting game: build a team, draft champions against a friend, assign your picks to your players, and watch the server simulate the match.

- Game design and rules: [league_draft_manager_game_spec.md](league_draft_manager_game_spec.md)
- Original generic spec it grew from: [league_simulator_game_spec.md](league_simulator_game_spec.md)
- Prototype the simulation is based on: [Game_Pick_Ban_Reference_Code.py](Game_Pick_Ban_Reference_Code.py)

## Run it

Requirements: Python 3.11+, Node 18+.

```bash
# backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt      # macOS/Linux: .venv/bin/pip
.venv/Scripts/python -m uvicorn app.main:app --reload  # http://127.0.0.1:8000

# frontend (second terminal)
cd frontend
npm install
npm run dev                                            # http://localhost:5173 (backend URL from VITE_API_URL, copy frontend/.env.example to .env)
```

Or build the web app once and let the backend serve everything on port 8000:

```bash
cd frontend && npm install && npm run build
cd ../backend && .venv/Scripts/python -m uvicorn app.main:app
```

To play alone, open the **Single Player** tab on the home page: you pick a team for each side and make every pick and ban yourself.

For multiplayer, register two accounts (use a second browser profile or a private window), create a lobby on the **Multiplayer** tab with one, and join it with the code from the other.

Copy `backend/.env.example` to `backend/.env` to set your own values (`.env` is git-ignored and must never be committed). Settings come from environment variables prefixed `LDM_` (see `backend/app/core/config.py`): `LDM_DATABASE_URL` (default `sqlite:///./league_draft_manager.db`), `LDM_SECRET_KEY` (**change it outside development**), `LDM_CORS_ORIGINS`. For PostgreSQL: `LDM_DATABASE_URL=postgresql+psycopg://user:pass@host/db`, then `alembic upgrade head`.

## Import players from Riot accounts (optional)

Turn a real League account into a player (Players page -> **Import from Riot**). It needs a Riot API key on the server:

1. Register a product at [developer.riotgames.com](https://developer.riotgames.com) and create a **personal** API key. (A plain development key also works but expires every 24 hours.)
2. Put it in `backend/.env`: `LDM_RIOT_API_KEY=RGAPI-...` and restart the backend. The key never leaves the server.

Without a key the import button is hidden and the rest of the game is unaffected. See section 19 of the spec for how stats are derived and the rate limits (a personal key allows about four imports per two minutes).

## Adding or editing champions

Champions come from `backend/app/data/seed/Champions.csv` (this folder is the one place to edit; the root `Data/` folder is just the original reference copy and is not read by the app) (plus win/pick rates from `ChampionStatistics.csv`, matched by name). To add one, append a row with the next free `Id` (156, 157, ...) and the champion's stats; to change one, edit its row.

A row with only `Id` and `Name` filled in is a **placeholder**: it reserves the champion but is not added to the game (the backend logs a warning) until you fill in the rest of the row.

The backend syncs the CSVs into the database **on every start**: new champions are added, changed values are updated, and nothing is ever deleted (so existing players and games are unaffected). To apply edits without restarting, or to preview them:

```bash
cd backend && .venv/Scripts/python -m scripts.sync_champions --dry-run   # show what would change
cd backend && .venv/Scripts/python -m scripts.sync_champions             # apply
```

## Test it

```bash
cd backend && .venv/Scripts/python -m pytest                   # engine, draft, API and WebSocket tests
cd backend && .venv/Scripts/python -m scripts.balance 1000     # balance suite: game length, win rates, comfort edge
cd backend && .venv/Scripts/python -m scripts.smoke_test       # full game against a running server (~35 s: waits out a real draft timeout)
cd frontend && npm test && npm run build
```

## Layout

| Path | What |
|---|---|
| `backend/app/game/` | The game engine: draft, lane phase, fights, objectives, structures, ranking. Pure Python, no web or database imports |
| `backend/app/services/`, `api/`, `websocket/` | Lobby/game state machine, team management, REST and WebSocket layer |
| `backend/app/data/seed/` | Default teams, players and champions (from `Data/`), loaded as read-only default content |
| `frontend/src/` | React app: lobby, draft, lane assignment, results, team/player/coach management |
| `Data/` | Original CSV data set (copied into `backend/app/data/seed/`) |
