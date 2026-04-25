"""Tests for blocking users and the open-conversation flow."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .models import BlockedUser


User = get_user_model()


class BlockingTests(TestCase):
    def setUp(self):
        Group.objects.get_or_create(name="User")
        self.alice = User.objects.create_user("alice", "a@a.com", "pw12345!")
        self.bob = User.objects.create_user("bob", "b@b.com", "pw12345!")

    def test_toggle_block_creates_and_removes(self):
        self.client.force_login(self.alice)
        url = reverse("moderation:toggle_block", args=[self.bob.id])
        self.client.post(url)
        self.assertTrue(BlockedUser.objects.filter(blocker=self.alice, blocked=self.bob).exists())
        self.client.post(url)
        self.assertFalse(BlockedUser.objects.filter(blocker=self.alice, blocked=self.bob).exists())

    def test_blocked_users_cannot_open_dm(self):
        BlockedUser.objects.create(blocker=self.alice, blocked=self.bob)
        self.client.force_login(self.bob)
        resp = self.client.get(reverse("dm:open_with", args=[self.alice.username]), follow=True)
        self.assertContains(resp, "cannot start a DM")
