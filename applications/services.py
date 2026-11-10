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
    """Delete an order (by its owner).
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
            paid = offer.coins_spent or (
                settings.OFFER_COST_COINS if offer.source == Offer.Source.ARCHITECT_APPLIED else 0
            )
            if paid:
                wallet, _ = Wallet.objects.get_or_create(architect=offer.architect)
                # Offers made before the amount was recorded cost the standard fee.
                refund_offer_coins(wallet, paid)
                from architects.navigation import dashboard_url
                from notifications.services import notify
                notify(
                    offer.architect, f"Mijoz e'lonni o'chirdi ({application.location}). {paid} tanga hisobingizga qaytarildi.",
                    dashboard_url(offer.architect, "store"),
                )
                refunded += 1
            offer.status = Offer.Status.REJECTED
            offer.decided_at = now
            offer.save(update_fields=["status", "decided_at"])
        application.status = Application.Status.CANCELLED

    application.deleted_at = timezone.now()
    application.auto_deleted = auto
    application.save(update_fields=["status", "deleted_at", "auto_deleted"])
    return refunded


def notify_new_order(application: Application) -> int:
    """A client just posted an order: every studio/freelancer who can take it gets a red number on
    their "E'lonlar bozori" tab. Returns how many were told."""
    from architects.models import ArchitectProfile
    from architects.navigation import dashboard_url
    from notifications.models import Notification

    what = application.get_service_type_display() or "Yangi loyiha"
    size = f", {application.size_m2} m²" if application.size_m2 else ""
    text = f"Yangi e'lon: {application.location} — {what}{size}."
    candidates = ArchitectProfile.objects.filter(
        approval_status=ArchitectProfile.ApprovalStatus.APPROVED,
    ).exclude(kind=ArchitectProfile.Kind.STUDIO_EMPLOYEE).select_related("user")
    rows = [
        Notification(user=profile.user, text=text, url=dashboard_url(profile, "market"))
        for profile in candidates if profile.can_take_offers
    ]
    Notification.objects.bulk_create(rows)
    return len(rows)


def reopen_audience_choice(application: Application) -> bool:
    """Take back "public" or "sent to one architect" so the owner can choose again. Only possible while
    nobody has applied / accepted (see Application.can_change_audience). Returns whether it was done."""
    from architects.navigation import dashboard_url
    from notifications.services import notify
    from offers.models import Offer

    if not application.can_change_audience:
        return False
    if application.publication == Application.Publication.DIRECT:
        for offer in application.offers.filter(status=Offer.Status.PENDING).select_related("architect__user"):
            notify(
                offer.architect, f"Mijoz e'lonni qaytarib oldi: {application.location}.",
                dashboard_url(offer.architect, "orders"),
            )
            offer.delete()
    application.publication = Application.Publication.DRAFT
    application.sent_to = None
    application.save(update_fields=["publication", "sent_to"])
    return True
