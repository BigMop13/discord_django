"""WebSocket consumers for channel chat (real-time messaging)."""

from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .models import Channel, ChannelMembership, Message, Reaction


def channel_group_name(channel_id: int) -> str:
    return f"chat_{channel_id}"


class ChannelChatConsumer(AsyncJsonWebsocketConsumer):
    """One consumer per (user, channel) pair.

    Inbound JSON shapes accepted from clients:
        {"action": "send", "body": "hi"}                          # text message
        {"action": "delete", "message_id": 42}                    # mod-only soft delete
        {"action": "react", "message_id": 42, "emoji": "\U0001f44d"}  # toggle reaction

    Image and audio uploads are sent over plain HTTP (multipart) so this
    consumer only needs to broadcast a "message.new" event after the upload
    view persists the message.
    """

    async def connect(self):
        self.channel_id = int(self.scope["url_route"]["kwargs"]["channel_id"])
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        if not await self._can_view(user, self.channel_id):
            await self.close(code=4403)
            return
        self.group_name = channel_group_name(self.channel_id)
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
            payload = await self._save_text_message(user, self.channel_id, body)
            if payload is not None:
                await self.channel_layer.group_send(
                    self.group_name, {"type": "message.new", "message": payload}
                )

        elif action == "delete":
            message_id = content.get("message_id")
            if not isinstance(message_id, int):
                return
            ok = await self._soft_delete(user, message_id)
            if ok:
                await self.channel_layer.group_send(
                    self.group_name,
                    {"type": "message.deleted", "message_id": message_id},
                )

        elif action == "react":
            message_id = content.get("message_id")
            emoji = (content.get("emoji") or "").strip()
            if not isinstance(message_id, int) or not emoji:
                return
            payload = await self._toggle_reaction(user, message_id, emoji)
            if payload is not None:
                await self.channel_layer.group_send(
                    self.group_name, {"type": "reaction.changed", "reaction": payload}
                )

    async def message_new(self, event):
        await self.send_json({"type": "message.new", "message": event["message"]})

    async def message_deleted(self, event):
        await self.send_json({"type": "message.deleted", "message_id": event["message_id"]})

    async def reaction_changed(self, event):
        await self.send_json({"type": "reaction.changed", "reaction": event["reaction"]})

    @database_sync_to_async
    def _can_view(self, user, channel_id: int) -> bool:
        try:
            ch = Channel.objects.get(pk=channel_id)
        except Channel.DoesNotExist:
            return False
        if ch.kind == Channel.Kind.PUBLIC:
            return True
        return ChannelMembership.objects.filter(channel=ch, user=user).exists()

    @database_sync_to_async
    def _save_text_message(self, user, channel_id: int, body: str):
        try:
            ch = Channel.objects.get(pk=channel_id)
        except Channel.DoesNotExist:
            return None
        if ch.kind == Channel.Kind.PRIVATE and not ChannelMembership.objects.filter(
            channel=ch, user=user
        ).exists():
            return None
        msg = Message.objects.create(
            channel=ch, author=user, body=body, kind=Message.Kind.TEXT
        )
        return _serialize_message(msg)

    @database_sync_to_async
    def _soft_delete(self, user, message_id: int) -> bool:
        try:
            msg = Message.objects.select_related("author").get(pk=message_id)
        except Message.DoesNotExist:
            return False
        if not (user.is_moderator() or msg.author_id == user.id):
            return False
        msg.is_deleted = True
        msg.body = ""
        msg.save(update_fields=["is_deleted", "body"])
        return True

    @database_sync_to_async
    def _toggle_reaction(self, user, message_id: int, emoji: str):
        try:
            msg = Message.objects.get(pk=message_id, channel_id=self.channel_id)
        except Message.DoesNotExist:
            return None
        existing = Reaction.objects.filter(message=msg, user=user, emoji=emoji).first()
        if existing:
            existing.delete()
            removed = True
        else:
            Reaction.objects.create(message=msg, user=user, emoji=emoji)
            removed = False
        counts = (
            Reaction.objects.filter(message=msg)
            .values("emoji")
            .order_by("emoji")
        )
        emoji_counts = {}
        for r in Reaction.objects.filter(message=msg).values_list("emoji", flat=True):
            emoji_counts[r] = emoji_counts.get(r, 0) + 1
        return {
            "message_id": msg.id,
            "emoji": emoji,
            "removed": removed,
            "user_id": user.id,
            "counts": emoji_counts,
        }


def _serialize_message(msg: Message) -> dict:
    """Compact JSON shape used by the chat client."""
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
