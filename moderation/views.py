"""Moderation views: block/unblock, message removal, report queue."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.permissions import moderator_required
from chat.models import Message
from direct_messages.models import DirectMessage

from .models import BlockedUser, Report


User = get_user_model()


@login_required
@require_POST
def toggle_block(request, user_id: int):
    """Toggle the request.user's block on `user_id`."""
    target = get_object_or_404(User, pk=user_id)
    if target == request.user:
        messages.warning(request, "You cannot block yourself.")
        return redirect("accounts:profile_self")
    existing = BlockedUser.objects.filter(blocker=request.user, blocked=target).first()
    if existing:
        existing.delete()
        messages.info(request, f"Unblocked {target.username}.")
    else:
        BlockedUser.objects.create(blocker=request.user, blocked=target)
        messages.warning(request, f"Blocked {target.username}.")
    return HttpResponseRedirect(
        request.META.get("HTTP_REFERER")
        or reverse("accounts:profile_detail", args=[target.username])
    )


@moderator_required
@require_POST
def delete_channel_message(request, message_id: int):
    """Mod/Admin removes a channel message."""
    msg = get_object_or_404(Message, pk=message_id)
    msg.is_deleted = True
    msg.body = ""
    msg.save(update_fields=["is_deleted", "body"])

    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from chat.consumers import channel_group_name

    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(
            channel_group_name(msg.channel_id),
            {"type": "message.deleted", "message_id": msg.id},
        )
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect("chat:channel_detail", slug=msg.channel.slug)


@moderator_required
@require_POST
def delete_dm_message(request, message_id: int):
    """Mod/Admin removes a DM message."""
    msg = get_object_or_404(DirectMessage, pk=message_id)
    msg.is_deleted = True
    msg.body = ""
    msg.save(update_fields=["is_deleted", "body"])

    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from direct_messages.consumers import dm_group_name

    layer = get_channel_layer()
    if layer is not None:
        async_to_sync(layer.group_send)(
            dm_group_name(msg.conversation_id),
            {"type": "dm.deleted", "message_id": msg.id},
        )
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect("dm:conversation_detail", conversation_id=msg.conversation_id)


@moderator_required
def dashboard(request):
    """Moderator landing page: open reports + block list overview."""
    open_reports = (
        Report.objects.filter(status=Report.Status.OPEN)
        .select_related("reporter", "target_user", "target_message")
        .order_by("-created_at")
    )
    blocks = BlockedUser.objects.select_related("blocker", "blocked").order_by(
        "-created_at"
    )[:50]
    recent_deleted = (
        Message.objects.filter(is_deleted=True)
        .select_related("author", "channel")
        .order_by("-created_at")[:25]
    )
    return render(
        request,
        "moderation/dashboard.html",
        {
            "open_reports": open_reports,
            "blocks": blocks,
            "recent_deleted": recent_deleted,
        },
    )


@login_required
@require_POST
def create_report(request):
    """Any user can file a report against a message or another user."""
    target_user_id = request.POST.get("target_user_id")
    target_message_id = request.POST.get("target_message_id")
    reason = (request.POST.get("reason") or "").strip()
    if not reason or (not target_user_id and not target_message_id):
        messages.error(request, "Please provide a reason and a target.")
        return redirect("core:home")
    Report.objects.create(
        reporter=request.user,
        target_user_id=target_user_id or None,
        target_message_id=target_message_id or None,
        reason=reason,
    )
    messages.success(request, "Report submitted. Thank you.")
    return HttpResponseRedirect(request.META.get("HTTP_REFERER") or reverse("core:home"))


@moderator_required
@require_POST
def resolve_report(request, report_id: int):
    decision = request.POST.get("decision", "resolved")
    report = get_object_or_404(Report, pk=report_id)
    if decision == "dismiss":
        report.status = Report.Status.DISMISSED
    else:
        report.status = Report.Status.RESOLVED
    report.save(update_fields=["status"])
    messages.success(request, "Report updated.")
    return redirect("moderation:dashboard")
