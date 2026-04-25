from django.contrib import admin

from .models import BlockedUser, Report


@admin.register(BlockedUser)
class BlockedUserAdmin(admin.ModelAdmin):
    list_display = ("blocker", "blocked", "created_at")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("reporter", "target_user", "target_message", "status", "created_at")
    list_filter = ("status",)
