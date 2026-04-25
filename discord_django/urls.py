"""Project URL configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("channels/", include("chat.urls", namespace="chat")),
    path("dm/", include("direct_messages.urls", namespace="dm")),
    path("moderation/", include("moderation.urls", namespace="moderation")),
    path("", include("core.urls", namespace="core")),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


handler404 = "core.views.page_not_found"
handler500 = "core.views.server_error"
