"""Top-level WebSocket URL routing for the project."""

from django.urls import path

from chat.consumers import ChannelChatConsumer
from chat.voice_consumers import VoiceRoomConsumer
from direct_messages.consumers import DMConsumer
from accounts.consumers import NotificationsConsumer, PresenceConsumer


websocket_urlpatterns = [
    path("ws/channel/<int:channel_id>/", ChannelChatConsumer.as_asgi()),
    path("ws/voice/<int:channel_id>/", VoiceRoomConsumer.as_asgi()),
    path("ws/dm/<int:conversation_id>/", DMConsumer.as_asgi()),
    path("ws/presence/", PresenceConsumer.as_asgi()),
    path("ws/notifications/", NotificationsConsumer.as_asgi()),
]
