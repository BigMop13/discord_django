"""HTTP views for direct messages and DM uploads."""

from __future__ import annotations

import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from moderation.models import BlockedUser

from .models import Conversation, DirectMessage


User = get_user_model()


@login_required
def conversation_list(request):
    convos = (
        Conversation.objects.filter(participants=request.user)
        .order_by("-last_message_at")
        .prefetch_related("participants")
    )
    enriched = []
    for c in convos:
        c.other_for = c.other_participant(request.user)
        enriched.append(c)
    return render(request, "direct_messages/list.html", {"conversations": enriched})


@login_required
def open_conversation_with(request, username: str):
    other = get_object_or_404(User, username__iexact=username)
    if other == request.user:
        messages.warning(request, "You cannot DM yourself.")
        return redirect("dm:conversation_list")
    if BlockedUser.is_blocked_between(request.user, other):
        messages.error(request, "You cannot start a DM with this user.")
        return redirect("dm:conversation_list")
    convo = Conversation.get_or_create_between(request.user, other)
    return redirect("dm:conversation_detail", conversation_id=convo.id)


@login_required
def conversation_detail(request, conversation_id: int):
    convo = get_object_or_404(
        Conversation.objects.filter(participants=request.user),
        pk=conversation_id,
    )
    other = convo.other_participant(request.user)
    blocked = (
        BlockedUser.objects.filter(blocker=request.user, blocked=other).exists()
        if other
        else False
    )
    is_blocked_by_them = (
        BlockedUser.objects.filter(blocker=other, blocked=request.user).exists()
        if other
        else False
    )
    history = (
        convo.messages.select_related("author").order_by("-created_at")[:100]
    )
    history = list(reversed(history))
    return render(
        request,
        "direct_messages/detail.html",
        {
            "conversation": convo,
            "other": other,
            "messages_history": history,
            "blocked_by_me": blocked,
            "blocked_by_them": is_blocked_by_them,
        },
    )


@login_required
@require_POST
def upload_dm_attachment(request, conversation_id: int):
    convo = get_object_or_404(
        Conversation.objects.filter(participants=request.user), pk=conversation_id
    )
    other = convo.other_participant(request.user)
    if other and BlockedUser.is_blocked_between(request.user, other):
        raise PermissionDenied("Conversation blocked.")

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
        msg_kind = DirectMessage.Kind.IMAGE
    elif kind_param == "audio":
        if ext not in settings.ALLOWED_AUDIO_EXTENSIONS:
            return JsonResponse({"detail": "Unsupported audio type."}, status=400)
        msg_kind = DirectMessage.Kind.AUDIO
    else:
        return JsonResponse({"detail": "Unknown kind."}, status=400)

    msg = DirectMessage.objects.create(
        conversation=convo,
        author=request.user,
        body=(request.POST.get("body") or "").strip(),
        kind=msg_kind,
        attachment=upload,
    )

    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from .consumers import _serialize, dm_group_name

    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(
            dm_group_name(convo.id),
            {"type": "dm.new", "message": _serialize(msg)},
        )

    return JsonResponse({"id": msg.id, "url": msg.attachment.url, "kind": msg.kind})
