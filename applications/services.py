from django.conf import settings
from django.db import transaction
from django.utils import timezone

from applications.models import Application


def live_offers(application: Application):
    """Offers still in play: waiting for an answer, or accepted and being worked on."""
    from offers.models import Offer

    return application.offers.filter(status__in=[Offer.Status.PENDING, Offer.Status.ACCEPTED])


@transaction.atomic
def delete_application(application: Application, auto: bool = False) -> int:
    """Delete an order (by its owner, or automatically when it expires).
    Returns how many architects were refunded.

    * The order disappears for the owner (the row is kept, marked deleted, so an
      architect's record of finished work stays intact).
    * An open or in-progress order is cancelled: every offer still in play is
      rejected, and each architect who paid coins to apply gets them back.
    * A finished order is only hidden; the architect keeps it in their history.
    """
    from offers.models import Offer
    from wallet.models import Wallet
    from wallet.services import refund_offer_coins

    application = Application.objects.select_for_update().get(pk=application.pk)
    if application.deleted_at is not None:
        return 0

    refunded = 0
    if application.status in (Application.Status.OPEN, Application.Status.IN_PROGRESS):
        now = timezone.now()
        for offer in live_offers(application).select_for_update().select_related("architect"):
            if offer.source == Offer.Source.ARCHITECT_APPLIED:
                wallet, _ = Wallet.objects.get_or_create(architect=offer.architect)
                # Offers made before the amount was recorded cost the standard fee.
                refund_offer_coins(wallet, offer.coins_spent or settings.OFFER_COST_COINS)
                refunded += 1
            offer.status = Offer.Status.REJECTED
            offer.decided_at = now
            offer.save(update_fields=["status", "decided_at"])
        application.status = Application.Status.CANCELLED

    application.deleted_at = timezone.now()
    application.auto_deleted = auto
    application.save(update_fields=["status", "deleted_at", "auto_deleted"])
    return refunded


def expire_stale_applications() -> int:
    """Delete every open order whose owner didn't confirm in time, refunding the
    architects who paid to apply. Returns how many orders were removed.

    Cheap when there is nothing to do, so it is called whenever orders are
    listed, and also by the ``expire_applications`` command / cron endpoint.
    """
    removed = 0
    for pk in list(Application.objects.stale().values_list("pk", flat=True)):
        application = Application.objects.get(pk=pk)
        if application in Application.objects.stale():   # re-check: it may have been confirmed meanwhile
            delete_application(application, auto=True)
            removed += 1
    return removed


def renew_application(application: Application) -> bool:
    """The owner confirms they are still searching: restart the countdown.

    Only possible once ``ORDER_RENEW_AFTER_DAYS`` have passed since the order was
    posted or last confirmed. Returns whether the countdown was restarted."""
    if application.deleted_at is None and application.can_renew:
        application.last_confirmed_at = timezone.now()
        application.save(update_fields=["last_confirmed_at"])
        return True
    return False
