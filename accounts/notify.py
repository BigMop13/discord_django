"""Helpers to push ephemeral notifications to a single user via Channels."""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def notifications_group(user_id: int) -> str:
    return f"notifications_{user_id}"


def push_to_user(user_id: int, payload: dict[str, Any]) -> None:
    """Fan out a single notification payload to every WS the user has open.

    Safe to call from synchronous Django code (views, signals). If the channel
    layer is unavailable (e.g. during migrations or in some test setups) this
    is a silent no-op so callers don't need to special-case it.
    """
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        notifications_group(user_id),
        {"type": "notify.message", "payload": payload},
    )


async def apush_to_user(user_id: int, payload: dict[str, Any]) -> None:
    """Async variant of `push_to_user` for use inside Channels consumers."""
    layer = get_channel_layer()
    if layer is None:
        return
    await layer.group_send(
        notifications_group(user_id),
        {"type": "notify.message", "payload": payload},
    )


def build_channel_payload(message, channel) -> dict[str, Any]:
    return {
        "kind": "channel",
        "target_id": channel.id,
        "channel_slug": channel.slug,
        "channel_name": channel.name,
        "author_username": message.author.username,
        "preview": _preview(message.body, message.kind),
        "kind_label": message.kind,
    }


def build_dm_payload(message, conversation) -> dict[str, Any]:
    return {
        "kind": "dm",
        "target_id": conversation.id,
        "conversation_id": conversation.id,
        "author_username": message.author.username,
        "preview": _preview(message.body, message.kind),
        "kind_label": message.kind,
    }


def _preview(body: str, kind: str) -> str:
    body = (body or "").strip()
    if not body:
        if kind == "image":
            return "(image)"
        if kind == "audio":
            return "(voice message)"
        return ""
    if len(body) > 80:
        return body[:77] + "..."
    return body
