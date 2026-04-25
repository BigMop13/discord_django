"""WebSocket consumer for 1-on-1 direct message conversations."""

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import Conversation, DirectMessage
from moderation.models import BlockedUser


def dm_group_name(conversation_id: int) -> str:
    return f"dm_{conversation_id}"


class DMConsumer(AsyncJsonWebsocketConsumer):
    """Real-time DM channel between exactly two users."""

    async def connect(self):
        self.conversation_id = int(self.scope["url_route"]["kwargs"]["conversation_id"])
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        if not await self._is_participant(user, self.conversation_id):
            await self.close(code=4403)
            return
        self.group_name = dm_group_name(self.conversation_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        user = self.scope["user"]

        if action == "send":
            body = (content.get("body") or "").strip()
            if not body:
                return
            payload = await self._save(user, self.conversation_id, body)
            if payload is not None:
                await self.channel_layer.group_send(
                    self.group_name, {"type": "dm.new", "message": payload}
                )

        elif action == "delete":
            message_id = content.get("message_id")
            if not isinstance(message_id, int):
                return
            ok = await self._soft_delete(user, message_id)
            if ok:
                await self.channel_layer.group_send(
                    self.group_name,
                    {"type": "dm.deleted", "message_id": message_id},
                )

    async def dm_new(self, event):
        await self.send_json({"type": "dm.new", "message": event["message"]})

    async def dm_deleted(self, event):
        await self.send_json({"type": "dm.deleted", "message_id": event["message_id"]})

    @database_sync_to_async
    def _is_participant(self, user, conversation_id: int) -> bool:
        return Conversation.objects.filter(pk=conversation_id, participants=user).exists()

    @database_sync_to_async
    def _save(self, user, conversation_id: int, body: str):
        try:
            convo = Conversation.objects.get(pk=conversation_id, participants=user)
        except Conversation.DoesNotExist:
            return None
        # Refuse to send if either party blocked the other.
        other = convo.other_participant(user)
        if other is not None and BlockedUser.objects.filter(
            blocker__in=[user, other], blocked__in=[user, other]
        ).exists():
            return None
        msg = DirectMessage.objects.create(
            conversation=convo,
            author=user,
            body=body,
            kind=DirectMessage.Kind.TEXT,
        )
        return _serialize(msg)

    @database_sync_to_async
    def _soft_delete(self, user, message_id: int) -> bool:
        try:
            msg = DirectMessage.objects.get(pk=message_id, conversation_id=self.conversation_id)
        except DirectMessage.DoesNotExist:
            return False
        if not (user.is_moderator() or msg.author_id == user.id):
            return False
        msg.is_deleted = True
        msg.body = ""
        msg.save(update_fields=["is_deleted", "body"])
        return True


def _serialize(msg: DirectMessage) -> dict:
    return {
        "id": msg.id,
        "body": msg.body,
        "kind": msg.kind,
        "author_id": msg.author_id,
        "author_username": msg.author.username,
        "author_avatar": msg.author.avatar.url if msg.author.avatar else "",
        "attachment_url": msg.attachment.url if msg.attachment else "",
        "created_at": msg.created_at.isoformat(),
        "is_deleted": msg.is_deleted,
    }
