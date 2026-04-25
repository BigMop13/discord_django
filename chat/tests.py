"""Tests covering channel access control and message permissions."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .models import Channel, ChannelMembership, Message


User = get_user_model()


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
