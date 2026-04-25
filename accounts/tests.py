"""Smoke tests for accounts: registration, login, role assignment."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse


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
