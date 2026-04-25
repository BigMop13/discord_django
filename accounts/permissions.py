"""Reusable role-based access mixins and decorators."""

from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class AdminRequiredMixin(LoginRequiredMixin):
    """Only Administrators (or superusers) may access the view."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not request.user.is_administrator():
            raise PermissionDenied("Administrator role required.")
        return super().dispatch(request, *args, **kwargs)


class ModeratorRequiredMixin(LoginRequiredMixin):
    """Moderators or Administrators may access the view."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if not request.user.is_moderator():
            raise PermissionDenied("Moderator role required.")
        return super().dispatch(request, *args, **kwargs)


def moderator_required(view_func):
    """Function-view decorator equivalent of `ModeratorRequiredMixin`."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_moderator():
            raise PermissionDenied("Moderator role required.")
        return view_func(request, *args, **kwargs)

    return _wrapped


def admin_required(view_func):
    """Function-view decorator equivalent of `AdminRequiredMixin`."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_administrator():
            raise PermissionDenied("Administrator role required.")
        return view_func(request, *args, **kwargs)

    return _wrapped
