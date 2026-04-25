"""Account models: a custom User with profile fields, presence, and roles."""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Project user.

    We override `email` to make it required and unique, and we add a small
    profile (avatar, bio) plus presence tracking so the UI can render
    online/offline status without an external service.
    """

    class Status(models.TextChoices):
        ONLINE = "online", "Online"
        AWAY = "away", "Away"
        OFFLINE = "offline", "Offline"

    email = models.EmailField(unique=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    bio = models.TextField(blank=True, max_length=500)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OFFLINE
    )
    last_seen = models.DateTimeField(default=timezone.now)

    REQUIRED_FIELDS = ["email"]

    def __str__(self) -> str:
        return self.username

    def is_administrator(self) -> bool:
        return self.is_superuser or self.groups.filter(name="Administrator").exists()

    def is_moderator(self) -> bool:
        # Administrators are implicitly moderators.
        return self.is_administrator() or self.groups.filter(name="Moderator").exists()

    @property
    def role_label(self) -> str:
        if self.is_administrator():
            return "Administrator"
        if self.is_moderator():
            return "Moderator"
        return "User"

    @property
    def avatar_url(self) -> str:
        if self.avatar:
            return self.avatar.url
        return ""

    @property
    def initials(self) -> str:
        name = (self.get_full_name() or self.username or "?").strip()
        parts = [p for p in name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    def is_online(self) -> bool:
        return self.status == self.Status.ONLINE
