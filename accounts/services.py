from django.utils import timezone

from accounts.models import User


def freeze_account(user: User, reason: str = "") -> None:
    """Block this account from logging in. Everything about it (profile,
    portfolio, offers, wallet, …) is left untouched — it just can't sign in
    until unfrozen. Both auth backends already refuse an inactive user
    (accounts/backends.py), including an already-logged-in session."""
    user.is_active = False
    user.frozen_at = timezone.now()
    user.frozen_reason = reason
    user.save(update_fields=["is_active", "frozen_at", "frozen_reason"])


def unfreeze_account(user: User) -> None:
    user.is_active = True
    user.frozen_at = None
    user.frozen_reason = ""
    user.save(update_fields=["is_active", "frozen_at", "frozen_reason"])
