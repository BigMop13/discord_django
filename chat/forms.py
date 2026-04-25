"""Forms for the chat app."""

from __future__ import annotations

from django import forms

from .models import Channel


class ChannelForm(forms.ModelForm):
    """Create a new channel."""

    class Meta:
        model = Channel
        fields = ("name", "description", "kind")
        widgets = {
            "description": forms.TextInput(),
        }
