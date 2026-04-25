"""Forms for registration and profile editing."""

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


User = get_user_model()


class RegistrationForm(UserCreationForm):
    """Sign-up form requiring username, email, and a password."""

    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_username(self) -> str:
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class ProfileEditForm(forms.ModelForm):
    """Allow users to update their public profile."""

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "bio", "avatar")
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 3, "maxlength": 500}),
        }

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].lower()
        qs = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Another user already uses this email.")
        return email
