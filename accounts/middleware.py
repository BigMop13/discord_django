"""Middleware that keeps `User.last_seen` and presence status fresh."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone


class UpdateLastSeenMiddleware:
    """Bump `last_seen` (and flip status to online) on each authenticated request.

    To avoid a write on every single request we only update if the existing
    `last_seen` value is older than `THRESHOLD_SECONDS`.
    """

    THRESHOLD_SECONDS = 60

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            now = timezone.now()
            if (now - user.last_seen) > timedelta(seconds=self.THRESHOLD_SECONDS):
                user.last_seen = now
                if user.status != user.Status.ONLINE:
                    user.status = user.Status.ONLINE
                    user.save(update_fields=["last_seen", "status"])
                else:
                    user.save(update_fields=["last_seen"])
        return response
