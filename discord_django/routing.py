"""Top-level WebSocket URL routing for the project."""

from django.urls import path

from chat.consumers import ChannelChatConsumer
from direct_messages.consumers import DMConsumer
from accounts.consumers import PresenceConsumer


websocket_urlpatterns = [
    path("ws/channel/<int:channel_id>/", ChannelChatConsumer.as_asgi()),
    path("ws/dm/<int:conversation_id>/", DMConsumer.as_asgi()),
    path("ws/presence/", PresenceConsumer.as_asgi()),
]
