"""1-on-1 direct message models."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Conversation(models.Model):
    """A 1-on-1 conversation between exactly two users."""

    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="dm_conversations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-last_message_at",)

    def __str__(self) -> str:
        names = list(self.participants.values_list("username", flat=True)[:2])
        return " <-> ".join(names) if names else f"Conversation #{self.pk}"

    def other_participant(self, user):
        return self.participants.exclude(pk=user.pk).first()

    @classmethod
    def get_or_create_between(cls, user_a, user_b) -> "Conversation":
        """Find the unique conversation between two users, creating one if needed."""
        if user_a.pk == user_b.pk:
            raise ValueError("Cannot start a DM with yourself.")
        existing = (
            cls.objects.filter(participants=user_a)
            .filter(participants=user_b)
            .first()
        )
        if existing:
            return existing
        convo = cls.objects.create()
        convo.participants.add(user_a, user_b)
        return convo


class DirectMessage(models.Model):
    """A single message inside a `Conversation`."""

    class Kind(models.TextChoices):
        TEXT = "text", "Text"
        IMAGE = "image", "Image"
        AUDIO = "audio", "Audio"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dm_sent"
    )
    body = models.TextField(blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TEXT)
    attachment = models.FileField(
        upload_to="dm_attachments/%Y/%m/", blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=("conversation", "created_at"))]

    def __str__(self) -> str:
        return f"{self.author}: {self.body[:30]}"

    def display_body(self) -> str:
        if self.is_deleted:
            return "[message deleted]"
        return self.body
