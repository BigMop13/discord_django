"""Signal handlers for the accounts app."""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User


@receiver(post_save, sender=User)
def assign_default_user_group(sender, instance: User, created: bool, **kwargs) -> None:
    """Put every brand-new user into the default 'User' group.

    The group is created by the data migration in `accounts/migrations`. We
    look it up lazily so the import order works regardless of when this
    signal is connected.
    """

    if not created:
        return
    if instance.is_superuser:
        # Superusers get the Administrator role for convenience.
        admin_group, _ = Group.objects.get_or_create(name="Administrator")
        instance.groups.add(admin_group)
        return
    user_group, _ = Group.objects.get_or_create(name="User")
    instance.groups.add(user_group)
