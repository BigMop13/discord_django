"""ASGI entry point that wires HTTP and WebSocket protocols.

Daphne (or any ASGI server) loads `application` from this module. WebSocket
routes are defined in `discord_django.routing`.
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "discord_django.settings")

# IMPORTANT: load the Django ASGI app first so that the app registry is ready
# before we import any consumer modules (which import models).
django_asgi_app = get_asgi_application()

from discord_django.routing import websocket_urlpatterns  # noqa: E402


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
