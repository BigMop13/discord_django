"""Authentication and profile views."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import UpdateView

from .forms import ProfileEditForm, RegistrationForm


User = get_user_model()


def register(request):
    """Create a new account and log the user in."""
    if request.user.is_authenticated:
        return redirect("core:home")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.status = User.Status.ONLINE
            user.last_seen = timezone.now()
            user.save(update_fields=["status", "last_seen"])
            login(request, user)
            messages.success(request, "Welcome! Your account has been created.")
            return redirect("core:home")
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile_self(request):
    """Show the logged-in user's own profile."""
    return render(request, "accounts/profile.html", {"profile_user": request.user, "is_self": True})


@login_required
def profile_detail(request, username: str):
    """Show another user's public profile."""
    profile_user = get_object_or_404(User, username__iexact=username)
    return render(
        request,
        "accounts/profile.html",
        {"profile_user": profile_user, "is_self": profile_user == request.user},
    )


class ProfileEditView(LoginRequiredMixin, UpdateView):
    """Let users edit their own profile."""

    model = User
    form_class = ProfileEditForm
    template_name = "accounts/profile_edit.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self) -> str:
        messages.success(self.request, "Profile updated.")
        return reverse("accounts:profile_self")
