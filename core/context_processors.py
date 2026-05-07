"""Template context processors used by the global sidebar."""

from __future__ import annotations

from chat.models import Channel
from direct_messages.models import Conversation


def sidebar_context(request):
    """Inject channels & DMs the user can see, for the persistent sidebar."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            "sidebar_text_channels": [],
            "sidebar_voice_channels": [],
            "sidebar_dms": [],
        }
    joined = Channel.objects.filter(members=request.user).order_by("name")[:50]
    text_channels = [c for c in joined if c.kind != Channel.Kind.VOICE]
    voice_channels = [c for c in joined if c.kind == Channel.Kind.VOICE]
    convos = (
        Conversation.objects.filter(participants=request.user)
        .order_by("-last_message_at")
        .prefetch_related("participants")[:15]
    )
    enriched = []
    for c in convos:
        c.other_for = c.other_participant(request.user)
        enriched.append(c)
    return {
        "sidebar_text_channels": text_channels,
        "sidebar_voice_channels": voice_channels,
        "sidebar_dms": enriched,
    }
