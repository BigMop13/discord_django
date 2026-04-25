"""Assign default permissions to the Administrator and Moderator role groups.

Without this migration, the role groups exist but carry no permissions, so
staff users dropped into the Django admin (e.g. the demo `admin` account) see
"You don't have permission to view or edit anything." This migration grants:

* Administrator -> full CRUD on every model in our apps (chat, accounts,
  direct_messages, moderation) plus group/user/permission management.
* Moderator     -> view/change/delete on messages and reports, view on users
  and channels, plus block/unblock users.

The User group intentionally receives no admin permissions; regular users
interact with the app through the web UI only.
"""

from __future__ import annotations

from django.db import migrations


ADMIN_APPS = ("accounts", "chat", "direct_messages", "moderation")
ADMIN_AUTH_MODELS = (("auth", "group"), ("auth", "permission"))


MODERATOR_PERMS = [
    # (app_label, model, codenames)
    ("chat", "message",            ("view", "change", "delete")),
    ("chat", "reaction",           ("view", "delete")),
    ("chat", "channel",            ("view",)),
    ("chat", "channelmembership",  ("view",)),
    ("direct_messages", "directmessage", ("view", "change", "delete")),
    ("direct_messages", "conversation",  ("view",)),
    ("accounts", "user",           ("view",)),
    ("moderation", "report",       ("view", "change", "delete")),
    ("moderation", "blockeduser",  ("view", "add", "delete")),
]


def _admin_perms(Permission, ContentType):
    qs = Permission.objects.none()
    for app_label in ADMIN_APPS:
        cts = ContentType.objects.filter(app_label=app_label)
        qs = qs | Permission.objects.filter(content_type__in=cts)
    for app_label, model in ADMIN_AUTH_MODELS:
        ct = ContentType.objects.filter(app_label=app_label, model=model).first()
        if ct is not None:
            qs = qs | Permission.objects.filter(content_type=ct)
    return qs.distinct()


def _moderator_perms(Permission, ContentType):
    ids = []
    for app_label, model, actions in MODERATOR_PERMS:
        ct = ContentType.objects.filter(app_label=app_label, model=model).first()
        if ct is None:
            continue
        for action in actions:
            perm = Permission.objects.filter(
                content_type=ct, codename=f"{action}_{model}"
            ).first()
            if perm is not None:
                ids.append(perm.pk)
    return Permission.objects.filter(pk__in=ids)


def assign_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    admin_group, _ = Group.objects.get_or_create(name="Administrator")
    moderator_group, _ = Group.objects.get_or_create(name="Moderator")
    Group.objects.get_or_create(name="User")

    admin_group.permissions.set(_admin_perms(Permission, ContentType))
    moderator_group.permissions.set(_moderator_perms(Permission, ContentType))


def clear_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ("Administrator", "Moderator"):
        group = Group.objects.filter(name=name).first()
        if group is not None:
            group.permissions.clear()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_seed_role_groups"),
        # Wait for every app's tables (and therefore content types) to exist
        # so that the permissions we look up are guaranteed to be created.
        ("chat", "0001_initial"),
        ("direct_messages", "0001_initial"),
        ("moderation", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(assign_permissions, clear_permissions),
    ]
