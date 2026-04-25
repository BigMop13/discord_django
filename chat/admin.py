from django.contrib import admin

from .models import Channel, ChannelMembership, Message, Reaction


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "owner", "created_at")
    list_filter = ("kind",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ChannelMembership)
class ChannelMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "channel", "joined_at", "is_owner")
    list_filter = ("is_owner",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("channel", "author", "kind", "is_deleted", "created_at")
    list_filter = ("kind", "is_deleted")
    search_fields = ("body", "author__username")


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ("message", "user", "emoji", "created_at")
    search_fields = ("emoji",)
