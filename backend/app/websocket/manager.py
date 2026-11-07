"""WebSocket connection registry (spec section 25).

WebSockets only *notify* clients; REST stays authoritative for every mutation and for full state.
Channels are a game id (the players of one game) or season_channel(id) (everyone on a season's hub).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Union

from fastapi import WebSocket

log = logging.getLogger(__name__)
Channel = Union[int, str]


def season_channel(season_id: int) -> str:
    return f"season:{season_id}"


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[Channel, list[tuple[WebSocket, int]]] = defaultdict(list)

    def online_users(self, game_id: Channel) -> set[int]:
        return {uid for _, uid in self._connections.get(game_id, [])}

    async def connect(self, game_id: Channel, user_id: int, websocket: WebSocket) -> bool:
        """Register a connection. Returns True if this is the user's first connection to the game."""
        await websocket.accept()
        first = user_id not in self.online_users(game_id)
        self._connections[game_id].append((websocket, user_id))
        return first

    def disconnect(self, game_id: Channel, user_id: int, websocket: WebSocket) -> bool:
        """Unregister. Returns True if the user now has no connections left for the game."""
        conns = self._connections.get(game_id, [])
        self._connections[game_id] = [(w, u) for w, u in conns if w is not websocket]
        if not self._connections[game_id]:
            self._connections.pop(game_id, None)
        return user_id not in self.online_users(game_id)

    async def broadcast(self, game_id: Channel, event: dict, exclude: WebSocket | None = None) -> None:
        for websocket, user_id in list(self._connections.get(game_id, [])):
            if websocket is exclude:
                continue
            try:
                await websocket.send_json(event)
            except Exception:  # connection died; the receive loop will clean it up
                log.debug("dropping dead websocket for game %s user %s", game_id, user_id)
                self._connections[game_id] = [(w, u) for w, u in self._connections.get(game_id, [])
                                              if w is not websocket]

    async def publish(self, events: list[dict]) -> None:
        """Game events go to the game's players; season events to the season's hub (once each per batch, however
        many games of the season just finished)."""
        seasons_sent: set[int] = set()
        for event in events:
            if "game_id" in event:
                await self.broadcast(event["game_id"], event)
            elif "season_id" in event and event["season_id"] not in seasons_sent:
                seasons_sent.add(event["season_id"])
                await self.broadcast(season_channel(event["season_id"]), event)


manager = ConnectionManager()
