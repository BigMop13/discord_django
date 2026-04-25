"""Moderation models: blocking other users and (optional) reporting."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class BlockedUser(models.Model):
    """`blocker` has blocked `blocked` and refuses to receive their DMs."""

    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="blocking",
        on_delete=models.CASCADE,
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="blocked_by",
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("blocker", "blocked")

    def __str__(self) -> str:
        return f"{self.blocker} blocked {self.blocked}"

    @classmethod
    def is_blocked_between(cls, user_a, user_b) -> bool:
        return cls.objects.filter(
            blocker__in=[user_a, user_b], blocked__in=[user_a, user_b]
        ).exists()


class Report(models.Model):
    """Optional: a user reports another user or message to moderators."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="reports_filed",
        on_delete=models.CASCADE,
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="reports_received",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    target_message = models.ForeignKey(
        "chat.Message",
        related_name="reports",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OPEN
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Report by {self.reporter} ({self.status})"
