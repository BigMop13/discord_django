"""Smoke tests for accounts: registration, login, role assignment."""

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.test import TestCase, TransactionTestCase
from django.urls import path, reverse

from chat.consumers import ChannelChatConsumer
from chat.models import Channel, ChannelMembership
from direct_messages.consumers import DMConsumer
from direct_messages.models import Conversation

from .consumers import NotificationsConsumer


User = get_user_model()


class RegistrationTests(TestCase):
    def test_register_creates_user_in_default_group(self):
        resp = self.client.post(
            reverse("accounts:register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password1": "complex-pass-123!",
                "password2": "complex-pass-123!",
            },
        )
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(username="newuser")
        self.assertTrue(user.groups.filter(name="User").exists())
        self.assertFalse(user.is_administrator())
        self.assertFalse(user.is_moderator())

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username="u1", email="dup@example.com", password="x")
        resp = self.client.post(
            reverse("accounts:register"),
            {
                "username": "u2",
                "email": "dup@example.com",
                "password1": "complex-pass-123!",
                "password2": "complex-pass-123!",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "email already exists")

    def test_role_helpers(self):
        u = User.objects.create_user(username="a", email="a@a.com", password="x")
        admin_group, _ = Group.objects.get_or_create(name="Administrator")
        u.groups.add(admin_group)
        self.assertTrue(u.is_administrator())
        self.assertTrue(u.is_moderator())


def _notify_app():
    """URLRouter combining chat, dm, and notifications WS routes for tests."""
    return URLRouter([
        path("ws/notifications/", NotificationsConsumer.as_asgi()),
        path("ws/channel/<int:channel_id>/", ChannelChatConsumer.as_asgi()),
        path("ws/dm/<int:conversation_id>/", DMConsumer.as_asgi()),
    ])


class NotificationsConsumerTests(TransactionTestCase):
    """End-to-end push tests: chat/DM consumer -> notifications consumer."""

    def setUp(self):
        Group.objects.get_or_create(name="User")
        self.alice = User.objects.create_user("notif_alice", "na@a.com", "pw12345!")
        self.bob = User.objects.create_user("notif_bob", "nb@b.com", "pw12345!")
        self.carol = User.objects.create_user("notif_carol", "nc@c.com", "pw12345!")

        self.public = Channel.objects.create(
            name="general", kind=Channel.Kind.PUBLIC, owner=self.alice
        )
        ChannelMembership.objects.create(
            channel=self.public, user=self.alice, is_owner=True
        )
        ChannelMembership.objects.create(channel=self.public, user=self.bob)
        # carol is intentionally NOT a member of self.public

        self.convo = Conversation.objects.create()
        self.convo.participants.add(self.alice, self.bob)

    async def _connect_notif(self, user):
        comm = WebsocketCommunicator(_notify_app(), "/ws/notifications/")
        comm.scope["user"] = user
        connected, _ = await comm.connect()
        return comm, connected

    async def _connect_chat(self, channel_id, user):
        comm = WebsocketCommunicator(_notify_app(), f"/ws/channel/{channel_id}/")
        comm.scope["user"] = user
        connected, _ = await comm.connect()
        return comm, connected

    async def _connect_dm(self, conversation_id, user):
        comm = WebsocketCommunicator(_notify_app(), f"/ws/dm/{conversation_id}/")
        comm.scope["user"] = user
        connected, _ = await comm.connect()
        return comm, connected

    async def test_anonymous_user_is_rejected(self):
        comm = WebsocketCommunicator(_notify_app(), "/ws/notifications/")
        comm.scope["user"] = AnonymousUser()
        connected, _ = await comm.connect()
        self.assertFalse(connected)

    async def test_channel_message_notifies_other_members(self):
        bob_notif, ok = await self._connect_notif(self.bob)
        self.assertTrue(ok)
        carol_notif, ok2 = await self._connect_notif(self.carol)
        self.assertTrue(ok2)

        alice_chat, _ = await self._connect_chat(self.public.id, self.alice)
        await alice_chat.send_json_to({"action": "send", "body": "hi everyone"})

        msg = await bob_notif.receive_json_from()
        self.assertEqual(msg["type"], "notification")
        self.assertEqual(msg["payload"]["kind"], "channel")
        self.assertEqual(msg["payload"]["target_id"], self.public.id)
        self.assertEqual(msg["payload"]["author_username"], "notif_alice")
        self.assertEqual(msg["payload"]["preview"], "hi everyone")

        self.assertTrue(await carol_notif.receive_nothing(timeout=0.3))

        await alice_chat.disconnect()
        await bob_notif.disconnect()
        await carol_notif.disconnect()

    async def test_channel_author_does_not_notify_self(self):
        alice_notif, _ = await self._connect_notif(self.alice)
        alice_chat, _ = await self._connect_chat(self.public.id, self.alice)
        await alice_chat.send_json_to({"action": "send", "body": "hello"})

        self.assertTrue(await alice_notif.receive_nothing(timeout=0.3))

        await alice_chat.disconnect()
        await alice_notif.disconnect()

    async def test_dm_message_notifies_other_participant(self):
        bob_notif, _ = await self._connect_notif(self.bob)
        alice_dm, _ = await self._connect_dm(self.convo.id, self.alice)
        await alice_dm.send_json_to({"action": "send", "body": "yo bob"})

        msg = await bob_notif.receive_json_from()
        self.assertEqual(msg["type"], "notification")
        self.assertEqual(msg["payload"]["kind"], "dm")
        self.assertEqual(msg["payload"]["target_id"], self.convo.id)
        self.assertEqual(msg["payload"]["author_username"], "notif_alice")
        self.assertEqual(msg["payload"]["preview"], "yo bob")

        await alice_dm.disconnect()
        await bob_notif.disconnect()
