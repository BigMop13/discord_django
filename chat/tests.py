"""Tests covering channel access control and message permissions."""

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.test import TestCase, TransactionTestCase
from django.urls import path, reverse

from .models import Channel, ChannelMembership, Message
from .voice_consumers import VoiceRoomConsumer, _voice_rooms


User = get_user_model()


def _voice_app():
    return URLRouter([
        path("ws/voice/<int:channel_id>/", VoiceRoomConsumer.as_asgi()),
    ])


class ChannelAccessTests(TestCase):
    def setUp(self):
        Group.objects.get_or_create(name="User")
        self.alice = User.objects.create_user("alice", "alice@x.com", "pw12345!")
        self.bob = User.objects.create_user("bob", "bob@x.com", "pw12345!")
        self.public = Channel.objects.create(
            name="general", description="hi", kind=Channel.Kind.PUBLIC, owner=self.alice
        )
        self.private = Channel.objects.create(
            name="staff", description="ssh", kind=Channel.Kind.PRIVATE, owner=self.alice
        )
        ChannelMembership.objects.create(channel=self.public, user=self.alice, is_owner=True)
        ChannelMembership.objects.create(channel=self.private, user=self.alice, is_owner=True)

    def test_public_channel_visible_to_anyone_logged_in(self):
        self.client.force_login(self.bob)
        resp = self.client.get(reverse("chat:channel_detail", args=[self.public.slug]))
        self.assertEqual(resp.status_code, 200)

    def test_private_channel_hidden_from_non_members(self):
        self.client.force_login(self.bob)
        resp = self.client.get(reverse("chat:channel_detail", args=[self.private.slug]))
        self.assertEqual(resp.status_code, 403)

    def test_join_public_channel(self):
        self.client.force_login(self.bob)
        resp = self.client.post(reverse("chat:channel_join", args=[self.public.slug]))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(self.public.is_member(self.bob))

    def test_join_private_channel_blocked_for_regular_user(self):
        self.client.force_login(self.bob)
        resp = self.client.post(reverse("chat:channel_join", args=[self.private.slug]))
        self.assertEqual(resp.status_code, 403)


class MessageDeletionTests(TestCase):
    def setUp(self):
        Group.objects.get_or_create(name="User")
        mod_group, _ = Group.objects.get_or_create(name="Moderator")
        self.alice = User.objects.create_user("alice", "a@a.com", "pw12345!")
        self.mod = User.objects.create_user("mod", "m@m.com", "pw12345!")
        self.mod.groups.add(mod_group)
        self.bob = User.objects.create_user("bob", "b@b.com", "pw12345!")

        self.channel = Channel.objects.create(
            name="general", kind=Channel.Kind.PUBLIC, owner=self.alice
        )
        for u in (self.alice, self.mod, self.bob):
            ChannelMembership.objects.create(channel=self.channel, user=u)

        self.msg = Message.objects.create(channel=self.channel, author=self.alice, body="hi")

    def test_other_user_cannot_delete(self):
        self.client.force_login(self.bob)
        resp = self.client.post(reverse("chat:delete_message", args=[self.msg.id]))
        self.assertEqual(resp.status_code, 403)
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.is_deleted)

    def test_moderator_can_delete(self):
        self.client.force_login(self.mod)
        resp = self.client.post(reverse("chat:delete_message", args=[self.msg.id]))
        self.assertIn(resp.status_code, (200, 302))
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.is_deleted)

    def test_author_can_delete_own_message(self):
        self.client.force_login(self.alice)
        resp = self.client.post(reverse("chat:delete_message", args=[self.msg.id]))
        self.assertIn(resp.status_code, (200, 302))
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.is_deleted)


class VoiceChannelModelTests(TestCase):
    def test_voice_kind_is_a_valid_choice(self):
        Group.objects.get_or_create(name="User")
        owner = User.objects.create_user("owen", "o@o.com", "pw12345!")
        ch = Channel.objects.create(
            name="lounge", kind=Channel.Kind.VOICE, owner=owner
        )
        ch.refresh_from_db()
        self.assertEqual(ch.kind, "voice")

    def test_voice_channel_visible_without_membership(self):
        Group.objects.get_or_create(name="User")
        alice = User.objects.create_user("alice2", "a2@a.com", "pw12345!")
        bob = User.objects.create_user("bob2", "b2@b.com", "pw12345!")
        ch = Channel.objects.create(
            name="lounge", kind=Channel.Kind.VOICE, owner=alice
        )
        # voice channels behave like public for visibility
        self.assertTrue(ch.can_view(bob))


class VoiceConsumerTests(TransactionTestCase):
    """Async tests for the WebRTC signaling consumer.

    The server is just a relay, so we verify routing semantics:
    auth, kind validation, peer announcement and direct signal forwarding.
    """

    def setUp(self):
        # Module-level peer registry is shared across tests; clear it.
        _voice_rooms.clear()
        Group.objects.get_or_create(name="User")
        self.alice = User.objects.create_user("voice_alice", "va@a.com", "pw12345!")
        self.bob = User.objects.create_user("voice_bob", "vb@b.com", "pw12345!")
        self.voice = Channel.objects.create(
            name="lounge", kind=Channel.Kind.VOICE, owner=self.alice
        )
        self.text = Channel.objects.create(
            name="general", kind=Channel.Kind.PUBLIC, owner=self.alice
        )

    async def _connect(self, channel_id, user):
        comm = WebsocketCommunicator(_voice_app(), f"/ws/voice/{channel_id}/")
        comm.scope["user"] = user
        connected, _code = await comm.connect()
        return comm, connected

    async def test_anonymous_user_is_rejected(self):
        comm = WebsocketCommunicator(
            _voice_app(), f"/ws/voice/{self.voice.id}/"
        )
        comm.scope["user"] = AnonymousUser()
        connected, _ = await comm.connect()
        self.assertFalse(connected)

    async def test_non_voice_channel_is_rejected(self):
        comm, connected = await self._connect(self.text.id, self.alice)
        self.assertFalse(connected)

    async def test_peer_list_and_peer_joined(self):
        a, ok_a = await self._connect(self.voice.id, self.alice)
        self.assertTrue(ok_a)
        peer_list_a = await a.receive_json_from()
        self.assertEqual(peer_list_a["type"], "peer.list")
        self.assertEqual(peer_list_a["peers"], [])

        b, ok_b = await self._connect(self.voice.id, self.bob)
        self.assertTrue(ok_b)
        peer_list_b = await b.receive_json_from()
        self.assertEqual(peer_list_b["type"], "peer.list")
        self.assertEqual(len(peer_list_b["peers"]), 1)
        self.assertEqual(peer_list_b["peers"][0]["user_id"], self.alice.id)

        peer_joined_at_a = await a.receive_json_from()
        self.assertEqual(peer_joined_at_a["type"], "peer.joined")
        self.assertEqual(peer_joined_at_a["peer"]["user_id"], self.bob.id)

        await a.disconnect()
        await b.disconnect()

    async def test_signal_is_forwarded_to_target_only(self):
        a, _ = await self._connect(self.voice.id, self.alice)
        await a.receive_json_from()  # peer.list

        b, _ = await self._connect(self.voice.id, self.bob)
        peer_list_b = await b.receive_json_from()
        a_peer_id = peer_list_b["peers"][0]["peer_id"]

        peer_joined_at_a = await a.receive_json_from()
        b_peer_id = peer_joined_at_a["peer"]["peer_id"]

        await b.send_json_to({
            "action": "signal",
            "target": a_peer_id,
            "data": {"type": "sdp", "sdp": "test-offer"},
        })

        msg_at_a = await a.receive_json_from()
        self.assertEqual(msg_at_a["type"], "signal")
        self.assertEqual(msg_at_a["from"], b_peer_id)
        self.assertEqual(msg_at_a["data"]["sdp"], "test-offer")

        # Signals must NOT echo back to the sender.
        self.assertTrue(await b.receive_nothing(timeout=0.3))

        await a.disconnect()
        await b.disconnect()

    async def test_mute_event_is_broadcast_to_group(self):
        a, _ = await self._connect(self.voice.id, self.alice)
        await a.receive_json_from()  # peer.list

        b, _ = await self._connect(self.voice.id, self.bob)
        await b.receive_json_from()  # peer.list
        await a.receive_json_from()  # peer.joined

        await a.send_json_to({"action": "mute", "is_muted": True})

        msg_at_a = await a.receive_json_from()
        self.assertEqual(msg_at_a["type"], "peer.muted")
        self.assertTrue(msg_at_a["is_muted"])

        msg_at_b = await b.receive_json_from()
        self.assertEqual(msg_at_b["type"], "peer.muted")
        self.assertTrue(msg_at_b["is_muted"])

        await a.disconnect()
        await b.disconnect()

    async def test_disconnect_announces_peer_left(self):
        a, _ = await self._connect(self.voice.id, self.alice)
        await a.receive_json_from()  # peer.list

        b, _ = await self._connect(self.voice.id, self.bob)
        peer_list_b = await b.receive_json_from()
        b_sees_a = peer_list_b["peers"][0]["peer_id"]

        await a.receive_json_from()  # peer.joined (bob)

        await a.disconnect()

        msg_at_b = await b.receive_json_from()
        self.assertEqual(msg_at_b["type"], "peer.left")
        self.assertEqual(msg_at_b["peer_id"], b_sees_a)

        await b.disconnect()
