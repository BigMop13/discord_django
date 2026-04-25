from django.urls import path

from . import views


app_name = "moderation"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("users/<int:user_id>/toggle-block/", views.toggle_block, name="toggle_block"),
    path("messages/<int:message_id>/delete/", views.delete_channel_message, name="delete_channel_message"),
    path("dm-messages/<int:message_id>/delete/", views.delete_dm_message, name="delete_dm_message"),
    path("reports/create/", views.create_report, name="create_report"),
    path("reports/<int:report_id>/resolve/", views.resolve_report, name="resolve_report"),
]
