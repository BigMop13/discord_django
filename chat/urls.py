from django.urls import path

from . import views


app_name = "chat"

urlpatterns = [
    path("", views.channel_list, name="channel_list"),
    path("create/", views.channel_create, name="channel_create"),
    path("<slug:slug>/", views.channel_detail, name="channel_detail"),
    path("<slug:slug>/join/", views.channel_join, name="channel_join"),
    path("<slug:slug>/leave/", views.channel_leave, name="channel_leave"),
    path("<slug:slug>/manage/", views.channel_manage, name="channel_manage"),
    path("<slug:slug>/upload/", views.upload_attachment, name="upload_attachment"),
    path("messages/<int:message_id>/delete/", views.delete_message, name="delete_message"),
    path("messages/<int:message_id>/react/", views.react_message, name="react_message"),
]
