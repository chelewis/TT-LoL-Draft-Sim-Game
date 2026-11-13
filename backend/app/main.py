from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import admin, auth, games, lobbies, management, meta, notifications, public, seasons, series
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.dependencies import user_from_token
from app.data.seed_db import seed_database
from app.models import Game, Season
from app.services import game_service, season_match_service
from app.services.timeouts import timeout_loop
from app.websocket.manager import manager, season_channel, user_channel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # development convenience; production uses Alembic migrations
    with SessionLocal() as db:
        seed_database(db)
    manager.bind_loop(asyncio.get_running_loop())       # so worker threads can push notifications
    task = None
    if settings.run_timeout_task:
        task = asyncio.create_task(timeout_loop(SessionLocal, settings.timeout_poll_seconds))
    yield
    manager.bind_loop(None)
    if task:
        task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="League Draft Manager", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    for module in (auth, management, public, meta, lobbies, games, series, seasons, notifications, admin):
        app.include_router(module.router, prefix=API_PREFIX)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.websocket("/ws/games/{game_id}")
    async def game_socket(websocket: WebSocket, game_id: int, token: str = ""):
        with SessionLocal() as db:
            user = user_from_token(db, token)
            game = db.get(Game, game_id)
            allowed = bool(user and game and game_service.side_of(game, user.id))
            side = game_service.side_of(game, user.id) if allowed else None
        if not allowed:
            await websocket.close(code=4403)
            return
        first = await manager.connect(game_id, user.id, websocket)
        await websocket.send_json({"type": "CONNECTED", "game_id": game_id, "team": side})
        if first:
            await manager.broadcast(game_id, {"type": "PLAYER_RECONNECTED", "game_id": game_id, "team": side},
                                    exclude=websocket)
        try:
            while True:
                message = await websocket.receive_text()  # clients may send pings; nothing else is accepted
                if message == "ping":
                    await websocket.send_json({"type": "PONG"})
        except WebSocketDisconnect:
            pass
        finally:
            if manager.disconnect(game_id, user.id, websocket):
                await manager.broadcast(game_id, {"type": "PLAYER_DISCONNECTED", "game_id": game_id, "team": side})

    @app.websocket("/ws/seasons/{season_id}")
    async def season_socket(websocket: WebSocket, season_id: int, token: str = ""):
        """Season hub notifications (SEASON_UPDATED: refetch the season) for the creator and its managers."""
        with SessionLocal() as db:
            user = user_from_token(db, token)
            season = db.get(Season, season_id)
            allowed = bool(user and season and season_match_service.is_member(db, season, user.id))
        if not allowed:
            await websocket.close(code=4403)
            return
        channel = season_channel(season_id)
        await manager.connect(channel, user.id, websocket)
        await websocket.send_json({"type": "CONNECTED", "season_id": season_id})
        try:
            while True:
                if await websocket.receive_text() == "ping":
                    await websocket.send_json({"type": "PONG"})
        except WebSocketDisconnect:
            pass
        finally:
            manager.disconnect(channel, user.id, websocket)

    @app.websocket("/ws/me")
    async def user_socket(websocket: WebSocket, token: str = ""):
        """Your notifications (NOTIFICATION: refetch the inbox), in every tab you have open."""
        with SessionLocal() as db:
            user = user_from_token(db, token)
        if user is None:
            await websocket.close(code=4403)
            return
        channel = user_channel(user.id)
        await manager.connect(channel, user.id, websocket)
        await websocket.send_json({"type": "CONNECTED"})
        try:
            while True:
                if await websocket.receive_text() == "ping":
                    await websocket.send_json({"type": "PONG"})
        except WebSocketDisconnect:
            pass
        finally:
            manager.disconnect(channel, user.id, websocket)

    _serve_frontend(app)
    return app


def _serve_frontend(app: FastAPI) -> None:
    """If the web app has been built (npm run build), serve it so one process runs the whole game."""
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        return

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(("api/", "ws/")):
            raise HTTPException(status_code=404)
        target = (FRONTEND_DIST / path).resolve()
        if path and target.is_file() and FRONTEND_DIST in target.parents:
            return FileResponse(target)
        return FileResponse(index)   # client-side routes such as /game/12


app = create_app()
