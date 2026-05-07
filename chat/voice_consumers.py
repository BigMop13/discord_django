"""WebSocket signaling for voice channels (WebRTC mesh).

The server is a pure relay: it never touches audio. Clients exchange SDP
offers/answers and ICE candidates through ``signal`` messages routed by
``target`` peer id (the channel name of the target's WebSocket). Audio
flows peer-to-peer between browsers.

Inbound JSON shapes (client -> server):
    {"action": "signal", "target": "<peer_id>", "data": {...}}
    {"action": "mute", "is_muted": true|false}

Outbound JSON shapes (server -> client):
    {"type": "peer.list",   "peers": [{peer_id, user_id, username, avatar, is_muted}, ...]}
    {"type": "peer.joined", "peer":  {peer_id, user_id, ...}}
    {"type": "peer.left",   "peer_id": "<peer_id>"}
    {"type": "peer.muted",  "peer_id": "<peer_id>", "is_muted": bool}
    {"type": "signal",      "from":   "<peer_id>",  "data": {...}}
"""

from __future__ import annotations

import asyncio
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import Channel


def voice_group_name(channel_id: int) -> str:
    return f"voice_{channel_id}"


# FIXME: in-memory registry is single-process only. For multi-worker
# deployments swap this for a Redis-backed registry (and switch
# CHANNEL_LAYERS to channels-redis).
_voice_rooms: dict[int, dict[str, dict[str, Any]]] = {}
_voice_lock = asyncio.Lock()


async def _add_peer(channel_id: int, peer_id: str, info: dict) -> list[dict]:
    """Register a peer and return the list of peers that were already there."""
    async with _voice_lock:
        room = _voice_rooms.setdefault(channel_id, {})
        existing = [p for pid, p in room.items() if pid != peer_id]
        room[peer_id] = info
        return existing


async def _remove_peer(channel_id: int, peer_id: str) -> None:
    async with _voice_lock:
        room = _voice_rooms.get(channel_id)
        if room and peer_id in room:
            del room[peer_id]
            if not room:
                _voice_rooms.pop(channel_id, None)


async def _set_peer_mute(channel_id: int, peer_id: str, is_muted: bool) -> None:
    async with _voice_lock:
        room = _voice_rooms.get(channel_id, {})
        if peer_id in room:
            room[peer_id]["is_muted"] = is_muted


class VoiceRoomConsumer(AsyncJsonWebsocketConsumer):
    """One consumer per (user, voice channel) WebSocket connection.

    Each connection gets a unique ``peer_id`` (its Channels channel_name) so
    a single user across multiple tabs participates as multiple peers.
    """

    async def connect(self):
        self.channel_id = int(self.scope["url_route"]["kwargs"]["channel_id"])
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        ch = await self._get_voice_channel(self.channel_id)
        if ch is None:
            await self.close(code=4404)
            return

        self.peer_id = self.channel_name
        self.group_name = voice_group_name(self.channel_id)

        my_info = {
            "peer_id": self.peer_id,
            "user_id": user.id,
            "username": user.username,
            "avatar": user.avatar.url if user.avatar else "",
            "is_muted": False,
        }

        existing = await _add_peer(self.channel_id, self.peer_id, my_info)

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.send_json({"type": "peer.list", "peers": existing})

        await self.channel_layer.group_send(
            self.group_name,
            {"type": "peer.joined", "peer": my_info, "exclude": self.peer_id},
        )

    async def disconnect(self, code):
        if not hasattr(self, "peer_id"):
            return
        await _remove_peer(self.channel_id, self.peer_id)
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "peer.left", "peer_id": self.peer_id},
        )
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        if action == "signal":
            target = content.get("target")
            data = content.get("data")
            if not isinstance(target, str) or data is None:
                return
            await self.channel_layer.send(
                target,
                {
                    "type": "signal.forward",
                    "from_peer": self.peer_id,
                    "data": data,
                },
            )
        elif action == "mute":
            is_muted = bool(content.get("is_muted"))
            await _set_peer_mute(self.channel_id, self.peer_id, is_muted)
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "peer.muted",
                    "peer_id": self.peer_id,
                    "is_muted": is_muted,
                },
            )

    async def peer_joined(self, event):
        if event.get("exclude") == self.peer_id:
            return
        await self.send_json({"type": "peer.joined", "peer": event["peer"]})

    async def peer_left(self, event):
        if event.get("peer_id") == self.peer_id:
            return
        await self.send_json({"type": "peer.left", "peer_id": event["peer_id"]})

    async def peer_muted(self, event):
        await self.send_json(
            {
                "type": "peer.muted",
                "peer_id": event["peer_id"],
                "is_muted": event["is_muted"],
            }
        )

    async def signal_forward(self, event):
        await self.send_json(
            {
                "type": "signal",
                "from": event["from_peer"],
                "data": event["data"],
            }
        )

    @database_sync_to_async
    def _get_voice_channel(self, channel_id: int):
        try:
            ch = Channel.objects.get(pk=channel_id)
        except Channel.DoesNotExist:
            return None
        if ch.kind != Channel.Kind.VOICE:
            return None
        return ch
