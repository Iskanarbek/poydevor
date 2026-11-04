from notifications.models import Notification


def notify(user, text: str, url: str = "") -> None:
    """Add a notification for ``user`` (an account, or an ArchitectProfile — its account is used).
    Does nothing for someone who doesn't exist, so callers never have to check."""
    user = getattr(user, "user", user)
    if user is None:
        return
    Notification.objects.create(user=user, text=text[:300], url=url)


def unread_count(user) -> int:
    return Notification.objects.filter(user=user, is_read=False).count()
