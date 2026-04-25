"""URL routes for authentication and user profiles."""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views


app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
    path("profile/", views.profile_self, name="profile_self"),
    path("profile/edit/", views.ProfileEditView.as_view(), name="profile_edit"),
    path("u/<str:username>/", views.profile_detail, name="profile_detail"),
]
