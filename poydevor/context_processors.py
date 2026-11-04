from architects.models import ArchitectProfile


def architect_wallet(request):
    """Expose the logged-in architect's wallet to every template via base.html.

    Returns {"architect_wallet": wallet} for authenticated architect users that
    have completed onboarding (i.e. have both an architect_profile and a
    wallet). Returns {} for everyone else, including anonymous users, plain
    "user" role accounts, and architects who haven't been given a wallet yet.
    """
    user = getattr(request, "user", None)
    if (
        user is None
        or not user.is_authenticated
        or getattr(user, "role", None) != user.Role.ARCHITECT
    ):
        return {}

    profile = (
        ArchitectProfile.objects.select_related("wallet")
        .filter(user=user)
        .first()
    )
    if profile is None or not hasattr(profile, "wallet"):
        return {}
    return {"architect_wallet": profile.wallet}


def unread_notifications(request):
    """The number on the bell in the top bar."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    from notifications.models import Notification
    if getattr(user, "role", None) == "architect":
        from offers.services import notify_overdue_assignments
        notify_overdue_assignments(user)          # deadlines have no clock of their own: check when someone looks
    return {"unread_notifications_count": Notification.objects.filter(user=user, is_read=False).count()}
