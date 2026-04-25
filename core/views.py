"""Project-wide views: home page, search, and custom error handlers."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from chat.models import Channel


User = get_user_model()


@login_required
def home(request):
    """Landing page after login: a directory of public channels + DMs."""
    public_channels = (
        Channel.objects.filter(kind=Channel.Kind.PUBLIC).order_by("-created_at")[:12]
    )
    my_channels = (
        Channel.objects.filter(members=request.user).order_by("name")[:12]
    )
    online_users = User.objects.filter(status=User.Status.ONLINE).exclude(pk=request.user.pk)[:12]
    return render(
        request,
        "core/home.html",
        {
            "public_channels": public_channels,
            "my_channels": my_channels,
            "online_users": online_users,
        },
    )


@login_required
def search(request):
    """Search for users and channels by name."""
    q = (request.GET.get("q") or "").strip()
    users = []
    channels = []
    if q:
        users = User.objects.filter(
            Q(username__icontains=q) | Q(email__icontains=q)
        ).exclude(pk=request.user.pk)[:30]
        channels = Channel.objects.filter(
            Q(name__icontains=q) | Q(description__icontains=q)
        )[:30]
    return render(
        request,
        "core/search.html",
        {"q": q, "users": users, "channels": channels},
    )


def page_not_found(request, exception=None):
    return render(request, "404.html", status=404)


def server_error(request):
    return render(request, "500.html", status=500)
