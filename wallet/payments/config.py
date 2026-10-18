"""Which payment providers are switched on.

A provider is on only when *all* of its credentials are present in settings
(which read them from environment variables). Everything else in the payment
code asks these helpers instead of touching settings directly, so a missing or
half-filled configuration just turns that provider off instead of raising.
"""
from django.conf import settings

from wallet.models import PaymentOrder


def payme_config() -> dict:
    return getattr(settings, "PAYME", None) or {}


def click_config() -> dict:
    return getattr(settings, "CLICK", None) or {}


def payme_enabled() -> bool:
    config = payme_config()
    return bool(config.get("MERCHANT_ID") and config.get("KEY"))


def click_enabled() -> bool:
    config = click_config()
    return bool(config.get("SERVICE_ID") and config.get("MERCHANT_ID") and config.get("SECRET_KEY"))


def is_enabled(provider: str) -> bool:
    if provider == PaymentOrder.Provider.PAYME:
        return payme_enabled()
    if provider == PaymentOrder.Provider.CLICK:
        return click_enabled()
    return False


def enabled_providers() -> list[dict]:
    """Providers the "buy coins" page may offer, as ``{"key", "label"}``."""
    return [
        {"key": key, "label": label}
        for key, label in PaymentOrder.Provider.choices
        if is_enabled(key)
    ]
