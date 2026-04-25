"""WebSocket consumer that broadcasts user online/offline state."""

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .models import User


PRESENCE_GROUP = "presence"


class PresenceConsumer(AsyncJsonWebsocketConsumer):
    """One bidirectional channel that announces who is online.

    Connected clients receive `{"type": "presence", "user_id": int, "status": str}`
    messages whenever another user comes online or goes offline.
    """

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        await self.channel_layer.group_add(PRESENCE_GROUP, self.channel_name)
        await self.accept()
        await self._set_status(user, User.Status.ONLINE)
        await self._broadcast(user.id, User.Status.ONLINE)

    async def disconnect(self, code):
        user = self.scope.get("user")
        if user is not None and user.is_authenticated:
            await self._set_status(user, User.Status.OFFLINE)
            await self._broadcast(user.id, User.Status.OFFLINE)
        await self.channel_layer.group_discard(PRESENCE_GROUP, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Heartbeat: clients can ping `{"type": "ping"}` to keep status fresh.
        if content.get("type") == "ping":
            user = self.scope.get("user")
            if user is not None and user.is_authenticated:
                await self._touch(user)

    async def presence_event(self, event):
        await self.send_json({
            "type": "presence",
            "user_id": event["user_id"],
            "status": event["status"],
        })

    async def _broadcast(self, user_id: int, status: str) -> None:
        await self.channel_layer.group_send(
            PRESENCE_GROUP,
            {"type": "presence.event", "user_id": user_id, "status": status},
        )

    @database_sync_to_async
    def _set_status(self, user: User, status: str) -> None:
        user.status = status
        user.last_seen = timezone.now()
        user.save(update_fields=["status", "last_seen"])

    @database_sync_to_async
    def _touch(self, user: User) -> None:
        user.last_seen = timezone.now()
        user.save(update_fields=["last_seen"])
