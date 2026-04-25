from django.contrib import admin

from .models import Conversation, DirectMessage


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "last_message_at")


@admin.register(DirectMessage)
class DirectMessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "author", "kind", "is_deleted", "created_at")
    list_filter = ("kind", "is_deleted")
