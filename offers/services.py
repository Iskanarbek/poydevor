from django.conf import settings
from django.db import transaction
from django.utils import timezone

from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer, StudioAssignment
from wallet.services import spend_coins

OFFER_COST = settings.OFFER_COST_COINS
MAX_ACTIVE_OFFERS_PER_APPLICATION = 3


class MaxArchitectsReachedError(Exception):
    pass


class OfferAlreadyDecidedError(Exception):
    pass


class ArchitectNotAllowedError(Exception):
    """Only approved studios and freelancers can take part in projects."""


class AssignmentAlreadyTakenError(Exception):
    """Someone else claimed, or the owner already assigned, this order."""


class WorkerNotInStudioError(Exception):
    """The chosen employee doesn't belong to this studio."""


@transaction.atomic
def send_offer(application: Application, architect, source: str) -> Offer:
    if not architect.can_take_offers:
        raise ArchitectNotAllowedError("Bu arxitektor hozircha loyihalarda qatnasha olmaydi")

    pending_count = application.offers.select_for_update().filter(status=Offer.Status.PENDING).count()
    if pending_count >= MAX_ACTIVE_OFFERS_PER_APPLICATION:
        raise MaxArchitectsReachedError("Bu e'longa allaqachon 3 ta arxitektor qatnashmoqda")

    coins_spent = 0
    if source == Offer.Source.ARCHITECT_APPLIED:
        spend_coins(architect.wallet, OFFER_COST)
        coins_spent = OFFER_COST

    return Offer.objects.create(
        application=application, architect=architect, source=source, coins_spent=coins_spent,
    )


@transaction.atomic
def accept_offer(offer: Offer) -> None:
    updated = Application.objects.filter(
        pk=offer.application_id, status=Application.Status.OPEN,
    ).update(status=Application.Status.IN_PROGRESS)
    if updated == 0:
        raise OfferAlreadyDecidedError("Bu ariza bo'yicha qaror allaqachon qabul qilingan")

    offer.status = Offer.Status.ACCEPTED
    offer.decided_at = timezone.now()
    offer.save(update_fields=["status", "decided_at"])

    offer.application.offers.filter(status=Offer.Status.PENDING).exclude(pk=offer.pk).update(
        status=Offer.Status.REJECTED, decided_at=timezone.now(),
    )

    # A studio's win is a job for its employees: open it up so any of them can
    # claim it, or so the owner can hand it to someone specific.
    if offer.architect.kind == ArchitectProfile.Kind.STUDIO_OWNER:
        StudioAssignment.objects.get_or_create(offer=offer)


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


# --- studio ↔ employee order assignment -------------------------------------


def _check_same_studio(assignment: StudioAssignment, worker: ArchitectProfile) -> None:
    studio = getattr(assignment.offer.architect, "studio_owned", None)
    if worker.kind != ArchitectProfile.Kind.STUDIO_EMPLOYEE or studio is None or worker.studio_id != studio.id:
        raise WorkerNotInStudioError("Bu xodim ushbu studiyaga tegishli emas")


@transaction.atomic
def assign_worker(assignment: StudioAssignment, worker: ArchitectProfile, deadline=None) -> None:
    """The studio owner hands this order to a specific employee (whether it was
    open or already assigned to someone else)."""
    _check_same_studio(assignment, worker)
    assignment.worker = worker
    assignment.status = StudioAssignment.Status.ASSIGNED
    assignment.assigned_at = timezone.now()
    fields = ["worker", "status", "assigned_at"]
    if deadline is not None:
        assignment.deadline = deadline
        fields.append("deadline")
    assignment.save(update_fields=fields)


@transaction.atomic
def claim_assignment(assignment: StudioAssignment, worker: ArchitectProfile) -> None:
    """An employee takes an open order for themselves. Fails if someone beat
    them to it (or the owner already assigned it)."""
    _check_same_studio(assignment, worker)
    updated = StudioAssignment.objects.filter(pk=assignment.pk, status=StudioAssignment.Status.OPEN).update(
        worker=worker, status=StudioAssignment.Status.ASSIGNED, assigned_at=timezone.now(),
    )
    if not updated:
        raise AssignmentAlreadyTakenError("Bu buyurtma allaqachon biriktirilgan")


@transaction.atomic
def set_deadline(assignment: StudioAssignment, deadline) -> None:
    assignment.deadline = deadline
    assignment.save(update_fields=["deadline"])


@transaction.atomic
def mark_assignment_done(assignment: StudioAssignment) -> None:
    assignment.status = StudioAssignment.Status.DONE
    assignment.done_at = timezone.now()
    assignment.save(update_fields=["status", "done_at"])
