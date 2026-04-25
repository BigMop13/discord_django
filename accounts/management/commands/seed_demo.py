"""Populate the database with demo users, channels, and a few messages.

Usage::

    python manage.py seed_demo

Idempotent: re-running won't duplicate accounts or channels.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from chat.models import Channel, ChannelMembership, Message
from direct_messages.models import Conversation, DirectMessage


User = get_user_model()


DEMO_USERS = [
    # username, email, role group, password
    ("admin",     "admin@example.com",     "Administrator", "demopass123"),
    ("moderator", "mod@example.com",       "Moderator",     "demopass123"),
    ("alice",     "alice@example.com",     "User",          "demopass123"),
    ("bob",       "bob@example.com",       "User",          "demopass123"),
    ("carol",     "carol@example.com",     "User",          "demopass123"),
]

DEMO_CHANNELS = [
    ("general", "General chatter for everyone.",      "public"),
    ("random",  "Memes, jokes, off-topic.",           "public"),
    ("staff",   "Internal channel for moderators.",   "private"),
]


class Command(BaseCommand):
    help = "Create demo users, role groups, channels, and seed messages."

    @transaction.atomic
    def handle(self, *args, **options):
        for name in ("Administrator", "Moderator", "User"):
            Group.objects.get_or_create(name=name)

        users = {}
        for username, email, role, password in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": email},
            )
            if created:
                user.set_password(password)
                user.save()
            group = Group.objects.get(name=role)
            # `set` (not `add`) so demo users land in exactly one role group,
            # overriding the default "User" group attached by the post_save
            # signal when the account was first created.
            user.groups.set([group])

            # Sync staff/superuser flags every run so an upgraded migration is
            # picked up on existing demo databases without having to nuke them.
            if role == "Administrator":
                user.is_staff = True
                user.is_superuser = True
            elif role == "Moderator":
                user.is_staff = True
                user.is_superuser = False
            else:
                user.is_staff = False
                user.is_superuser = False
            user.save(update_fields=["is_staff", "is_superuser"])
            users[username] = user

        admin = users["admin"]

        for slug, desc, kind in DEMO_CHANNELS:
            channel, _ = Channel.objects.get_or_create(
                slug=slug,
                defaults={"name": slug, "description": desc, "kind": kind, "owner": admin},
            )
            for u in users.values():
                if kind == "private" and u.username not in ("admin", "moderator"):
                    continue
                ChannelMembership.objects.get_or_create(
                    channel=channel, user=u,
                    defaults={"is_owner": u.id == admin.id},
                )

        general = Channel.objects.get(slug="general")
        if not Message.objects.filter(channel=general).exists():
            Message.objects.create(channel=general, author=admin,
                                   body="Welcome to discord-ish!")
            Message.objects.create(channel=general, author=users["alice"],
                                   body="Hey everyone, glad to be here.")
            Message.objects.create(channel=general, author=users["bob"],
                                   body="What's up Alice 👋")

        convo = Conversation.get_or_create_between(users["alice"], users["bob"])
        if not convo.messages.exists():
            DirectMessage.objects.create(
                conversation=convo, author=users["alice"], body="Hey Bob!"
            )
            DirectMessage.objects.create(
                conversation=convo, author=users["bob"], body="Hi Alice 🙂"
            )

        self.stdout.write(self.style.SUCCESS(
            "Seeded demo data. Logins: admin / moderator / alice / bob / carol "
            "- password 'demopass123'.\n"
            "  admin     -> superuser, full Django admin access\n"
            "  moderator -> staff, can moderate via /admin/ and /moderation/\n"
            "  alice/bob/carol -> regular users (web UI only)"
        ))
