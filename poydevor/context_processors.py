def architect_wallet(request):
    """Expose the logged-in architect's wallet to every template via base.html.

    Returns {"architect_wallet": wallet} for authenticated architect users that
    have completed onboarding (i.e. have both an architect_profile and a
    wallet). Returns {} for everyone else, including anonymous users, plain
    "user" role accounts, and architects who haven't been given a wallet yet.
    """
    user = getattr(request, "user", None)
    if (
        user is not None
        and user.is_authenticated
        and getattr(user, "role", None) == user.Role.ARCHITECT
        and hasattr(user, "architect_profile")
        and hasattr(user.architect_profile, "wallet")
    ):
        return {"architect_wallet": user.architect_profile.wallet}
    return {}
