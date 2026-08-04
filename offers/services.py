from django.db import transaction
from django.utils import timezone

from applications.models import Application
from offers.models import Offer
from wallet.services import spend_coins

OFFER_COST = 20
MAX_ACTIVE_OFFERS_PER_APPLICATION = 3


class MaxArchitectsReachedError(Exception):
    pass


@transaction.atomic
def send_offer(application: Application, architect, source: str) -> Offer:
    pending_count = application.offers.select_for_update().filter(status=Offer.Status.PENDING).count()
    if pending_count >= MAX_ACTIVE_OFFERS_PER_APPLICATION:
        raise MaxArchitectsReachedError("Bu e'longa allaqachon 3 ta arxitektor qatnashmoqda")

    if source == Offer.Source.ARCHITECT_APPLIED:
        spend_coins(architect.wallet, OFFER_COST)

    return Offer.objects.create(application=application, architect=architect, source=source)


@transaction.atomic
def accept_offer(offer: Offer) -> None:
    offer.status = Offer.Status.ACCEPTED
    offer.decided_at = timezone.now()
    offer.save(update_fields=["status", "decided_at"])

    offer.application.offers.filter(status=Offer.Status.PENDING).exclude(pk=offer.pk).update(
        status=Offer.Status.REJECTED, decided_at=timezone.now(),
    )

    offer.application.status = Application.Status.IN_PROGRESS
    offer.application.save(update_fields=["status"])


@transaction.atomic
def reject_offer(offer: Offer) -> None:
    offer.status = Offer.Status.REJECTED
    offer.decided_at = timezone.now()
    offer.save(update_fields=["status", "decided_at"])


@transaction.atomic
def complete_offer(offer: Offer) -> None:
    offer.status = Offer.Status.COMPLETED
    offer.completed_at = timezone.now()
    offer.save(update_fields=["status", "completed_at"])

    offer.application.status = Application.Status.CLOSED
    offer.application.save(update_fields=["status"])

    architect = offer.architect
    architect.completed_projects_count += 1
    architect.save(update_fields=["completed_projects_count"])
