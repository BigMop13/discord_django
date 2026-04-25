from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "status", "is_staff", "is_superuser")
    list_filter = ("status", "is_staff", "is_superuser", "groups")
    fieldsets = UserAdmin.fieldsets + (
        ("Profile", {"fields": ("avatar", "bio", "status", "last_seen")}),
    )
