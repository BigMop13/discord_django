"""Chat-domain models: channels, memberships, messages, reactions."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Channel(models.Model):
    """A text chat room.

    `kind` distinguishes between fully open `public` rooms (anyone can read &
    join) and `private` rooms (membership required, owner controls invites).
    """

    class Kind(models.TextChoices):
        PUBLIC = "public", "Public"
        PRIVATE = "private", "Private"

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True)
    description = models.CharField(max_length=255, blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PUBLIC)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="owned_channels",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ChannelMembership",
        related_name="joined_channels",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "channel"
            slug = base
            i = 1
            while Channel.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("chat:channel_detail", args=[self.slug])

    def is_member(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        return ChannelMembership.objects.filter(channel=self, user=user).exists()

    def can_view(self, user) -> bool:
        if self.kind == self.Kind.PUBLIC:
            return True
        return self.is_member(user) or (user and user.is_authenticated and user.is_administrator())

    def can_post(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if self.kind == self.Kind.PUBLIC:
            # Public channels still require explicit join to keep state tidy.
            return self.is_member(user) or user.is_administrator()
        return self.is_member(user) or user.is_administrator()

    def can_manage(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        return user.is_administrator() or self.owner_id == user.id


class ChannelMembership(models.Model):
    """Through-model so we can track join time per (user, channel)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_owner = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "channel")

    def __str__(self) -> str:
        return f"{self.user} in {self.channel}"


class Message(models.Model):
    """A single message sent inside a channel."""

    class Kind(models.TextChoices):
        TEXT = "text", "Text"
        IMAGE = "image", "Image"
        AUDIO = "audio", "Audio"

    channel = models.ForeignKey(
        Channel, on_delete=models.CASCADE, related_name="messages"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="messages"
    )
    body = models.TextField(blank=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TEXT)
    attachment = models.FileField(upload_to="attachments/%Y/%m/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=("channel", "created_at"))]

    def __str__(self) -> str:
        return f"{self.author}: {self.body[:30]}"

    def display_body(self) -> str:
        if self.is_deleted:
            return "[message deleted]"
        return self.body


class Reaction(models.Model):
    """Emoji reaction attached to a channel message."""

    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="reactions"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    emoji = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user", "emoji")

    def __str__(self) -> str:
        return f"{self.user} :{self.emoji}: {self.message_id}"
