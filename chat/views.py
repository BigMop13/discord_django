"""HTTP views for channels and channel-message uploads/actions."""

from __future__ import annotations

import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import moderator_required

from .forms import ChannelForm
from .models import Channel, ChannelMembership, Message, Reaction


@login_required
def channel_list(request):
    """List all channels the user can see (public + ones they joined)."""
    public = Channel.objects.filter(kind=Channel.Kind.PUBLIC).order_by("name")
    joined_ids = list(
        ChannelMembership.objects.filter(user=request.user).values_list(
            "channel_id", flat=True
        )
    )
    private_joined = Channel.objects.filter(
        pk__in=joined_ids, kind=Channel.Kind.PRIVATE
    ).order_by("name")
    return render(
        request,
        "chat/channel_list.html",
        {
            "public_channels": public,
            "private_channels": private_joined,
            "joined_ids": set(joined_ids),
        },
    )


@login_required
def channel_create(request):
    if request.method == "POST":
        form = ChannelForm(request.POST)
        if form.is_valid():
            channel = form.save(commit=False)
            channel.owner = request.user
            channel.save()
            ChannelMembership.objects.create(
                channel=channel, user=request.user, is_owner=True
            )
            messages.success(request, f"Channel #{channel.name} created.")
            return redirect("chat:channel_detail", slug=channel.slug)
    else:
        form = ChannelForm()
    return render(request, "chat/channel_form.html", {"form": form})


@login_required
def channel_detail(request, slug: str):
    channel = get_object_or_404(Channel, slug=slug)
    if not channel.can_view(request.user):
        raise PermissionDenied("You don't have access to this private channel.")
    is_member = channel.is_member(request.user)
    history = (
        channel.messages.select_related("author")
        .prefetch_related("reactions")
        .order_by("-created_at")[:100]
    )
    history = list(reversed(history))
    members = (
        ChannelMembership.objects.filter(channel=channel)
        .select_related("user")
        .order_by("user__username")
    )
    return render(
        request,
        "chat/channel_detail.html",
        {
            "channel": channel,
            "messages_history": history,
            "members": members,
            "is_member": is_member,
            "can_post": channel.can_post(request.user),
            "can_manage": channel.can_manage(request.user),
        },
    )


@login_required
@require_POST
def channel_join(request, slug: str):
    channel = get_object_or_404(Channel, slug=slug)
    if channel.kind == Channel.Kind.PRIVATE and not request.user.is_administrator():
        raise PermissionDenied("Private channels are invite-only.")
    ChannelMembership.objects.get_or_create(channel=channel, user=request.user)
    messages.success(request, f"Joined #{channel.name}.")
    return redirect("chat:channel_detail", slug=channel.slug)


@login_required
@require_POST
def channel_leave(request, slug: str):
    channel = get_object_or_404(Channel, slug=slug)
    ChannelMembership.objects.filter(channel=channel, user=request.user).delete()
    messages.info(request, f"Left #{channel.name}.")
    return redirect("chat:channel_list")


@login_required
def channel_manage(request, slug: str):
    channel = get_object_or_404(Channel, slug=slug)
    if not channel.can_manage(request.user):
        raise PermissionDenied("Only the channel owner can manage it.")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "rename":
            new_name = request.POST.get("name", "").strip()
            new_desc = request.POST.get("description", "").strip()
            if new_name:
                channel.name = new_name
                channel.description = new_desc
                channel.save(update_fields=["name", "description"])
                messages.success(request, "Channel updated.")
        elif action == "kick":
            user_id = request.POST.get("user_id")
            if user_id:
                ChannelMembership.objects.filter(
                    channel=channel, user_id=user_id
                ).exclude(user=channel.owner).delete()
                messages.info(request, "Member removed.")
        elif action == "delete":
            channel.delete()
            messages.warning(request, "Channel deleted.")
            return redirect("chat:channel_list")
        return redirect("chat:channel_manage", slug=channel.slug)

    members = (
        ChannelMembership.objects.filter(channel=channel)
        .select_related("user")
        .order_by("user__username")
    )
    return render(
        request,
        "chat/channel_manage.html",
        {"channel": channel, "members": members},
    )


@login_required
@require_POST
def upload_attachment(request, slug: str):
    """Receive an image or audio attachment via multipart upload.

    Returns JSON describing the saved message; the client also receives the
    real-time `message.new` event via the WebSocket consumer (we re-publish
    here to the chat group).
    """
    channel = get_object_or_404(Channel, slug=slug)
    if not channel.can_post(request.user):
        raise PermissionDenied("You can't post in this channel.")

    upload = request.FILES.get("file")
    if not upload:
        return JsonResponse({"detail": "No file uploaded."}, status=400)
    if upload.size > settings.MAX_UPLOAD_SIZE_BYTES:
        return JsonResponse({"detail": "File too large."}, status=400)
    ext = os.path.splitext(upload.name)[1].lower()
    kind_param = request.POST.get("kind", "image").lower()
    if kind_param == "image":
        if ext not in settings.ALLOWED_IMAGE_EXTENSIONS:
            return JsonResponse({"detail": "Unsupported image type."}, status=400)
        msg_kind = Message.Kind.IMAGE
    elif kind_param == "audio":
        if ext not in settings.ALLOWED_AUDIO_EXTENSIONS:
            return JsonResponse({"detail": "Unsupported audio type."}, status=400)
        msg_kind = Message.Kind.AUDIO
    else:
        return JsonResponse({"detail": "Unknown attachment kind."}, status=400)

    body = (request.POST.get("body") or "").strip()
    msg = Message.objects.create(
        channel=channel,
        author=request.user,
        body=body,
        kind=msg_kind,
        attachment=upload,
    )

    _broadcast_new_message(channel.id, msg)

    return JsonResponse({"id": msg.id, "url": msg.attachment.url, "kind": msg.kind})


def _broadcast_new_message(channel_id: int, message: Message) -> None:
    """Send a `message.new` event into the WebSocket group for the channel."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from .consumers import _serialize_message, channel_group_name

    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        channel_group_name(channel_id),
        {"type": "message.new", "message": _serialize_message(message)},
    )


@login_required
@require_POST
def delete_message(request, message_id: int):
    """Soft-delete a channel message (author or moderator)."""
    msg = get_object_or_404(Message, pk=message_id)
    if not (request.user.is_moderator() or msg.author_id == request.user.id):
        raise PermissionDenied()
    msg.is_deleted = True
    msg.body = ""
    msg.save(update_fields=["is_deleted", "body"])

    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from .consumers import channel_group_name

    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(
            channel_group_name(msg.channel_id),
            {"type": "message.deleted", "message_id": msg.id},
        )

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect("chat:channel_detail", slug=msg.channel.slug)


@login_required
@require_POST
def react_message(request, message_id: int):
    """Toggle an emoji reaction on a channel message."""
    msg = get_object_or_404(Message, pk=message_id)
    if not msg.channel.can_view(request.user):
        raise PermissionDenied()
    emoji = (request.POST.get("emoji") or "").strip()
    if not emoji:
        return JsonResponse({"detail": "No emoji."}, status=400)
    existing = Reaction.objects.filter(message=msg, user=request.user, emoji=emoji).first()
    if existing:
        existing.delete()
    else:
        Reaction.objects.create(message=msg, user=request.user, emoji=emoji)

    counts = {}
    for r in Reaction.objects.filter(message=msg).values_list("emoji", flat=True):
        counts[r] = counts.get(r, 0) + 1

    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from .consumers import channel_group_name

    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(
            channel_group_name(msg.channel_id),
            {
                "type": "reaction.changed",
                "reaction": {
                    "message_id": msg.id,
                    "emoji": emoji,
                    "user_id": request.user.id,
                    "removed": existing is not None,
                    "counts": counts,
                },
            },
        )
    return JsonResponse({"counts": counts})
