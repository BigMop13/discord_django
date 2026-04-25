from django.urls import path

from . import views


app_name = "dm"

urlpatterns = [
    path("", views.conversation_list, name="conversation_list"),
    path("with/<str:username>/", views.open_conversation_with, name="open_with"),
    path("<int:conversation_id>/", views.conversation_detail, name="conversation_detail"),
    path("<int:conversation_id>/upload/", views.upload_dm_attachment, name="upload_attachment"),
]
