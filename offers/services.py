from datetime import date

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from django.urls import reverse

from applications.models import Application
from architects.models import ArchitectProfile
from architects.navigation import dashboard_url
from notifications.services import notify
from offers.models import Offer, StudioAssignment
from wallet.models import Wallet
from wallet.services import spend_coins

OFFER_COST = settings.OFFER_COST_COINS
INVITE_ACCEPT_COST = settings.INVITE_ACCEPT_COST_COINS
MAX_ACTIVE_OFFERS_PER_APPLICATION = 3


def _day(value) -> str:
    """A deadline as dd.mm.yyyy (it may arrive as a date or as the raw ISO text)."""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d.%m.%Y")


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

    offer = Offer.objects.create(
        application=application, architect=architect, source=source, coins_spent=coins_spent,
    )
    place = application.location
    if source == Offer.Source.USER_INVITED:
        notify(
            architect, f"Mijoz sizga loyiha yubordi: {place}. Qabul qilish yoki rad etishingiz mumkin.",
            dashboard_url(architect, "orders"),
        )
    else:
        notify(
            application.owner, f"{architect.display_name} e'loningizga ariza yubordi: {place}.",
            reverse("applications:detail", args=[application.pk]),
        )
    return offer


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

    others = list(
        offer.application.offers.filter(status=Offer.Status.PENDING).exclude(pk=offer.pk)
        .select_related("architect__user")
    )
    offer.application.offers.filter(status=Offer.Status.PENDING).exclude(pk=offer.pk).update(
        status=Offer.Status.REJECTED, decided_at=timezone.now(),
    )
    place = offer.application.location
    for other in others:
        notify(
            other.architect, f"Mijoz boshqa arxitektorni tanladi: {place}.", dashboard_url(other.architect, "orders"),
        )
    if offer.source == Offer.Source.ARCHITECT_APPLIED:      # the client accepted the architect's application
        notify(
            offer.architect, f"Arizangiz qabul qilindi: {place}. Mijoz bilan bog'lanishingiz mumkin.",
            dashboard_url(offer.architect, "orders"),
        )
    else:                                                    # the architect accepted the client's invitation
        notify(
            offer.application.owner, f"{offer.architect.display_name} taklifingizni qabul qildi: {place}.",
            reverse("applications:detail", args=[offer.application_id]),
        )

    # A studio's win is a job for its employees: open it up so any of them can
    # claim it, or so the owner can hand it to someone specific.
    if offer.architect.kind == ArchitectProfile.Kind.STUDIO_OWNER:
        _, created = StudioAssignment.objects.get_or_create(offer=offer)
        if created:
            staff = ArchitectProfile.objects.filter(
                kind=ArchitectProfile.Kind.STUDIO_EMPLOYEE, studio=offer.architect.studio_owned,
                approval_status=ArchitectProfile.ApprovalStatus.APPROVED,
            )
            for employee in staff:
                notify(
                    employee, f"Studiyaga yangi buyurtma keldi: {place}. Ochiq buyurtmalardan olishingiz mumkin.",
                    dashboard_url(employee, "open"),
                )


@transaction.atomic
def accept_invitation(offer: Offer) -> None:
    """An architect accepts a project a client sent to them: costs INVITE_ACCEPT_COST coins.
    Everything rolls back (coins included) if the order was already decided."""
    wallet, _ = Wallet.objects.get_or_create(architect=offer.architect)
    spend_coins(wallet, INVITE_ACCEPT_COST)
    accept_offer(offer)
    offer.coins_spent = INVITE_ACCEPT_COST
    offer.save(update_fields=["coins_spent"])


@transaction.atomic
def decline_invitation(offer: Offer) -> None:
    """The architect/studio says no to a client's invitation. The client is told, and the
    invitation is removed completely (it disappears from the architect's table)."""
    application = offer.application
    freed = application.publication == Application.Publication.DIRECT and application.sent_to_id == offer.architect_id
    notify(
        application.owner,
        f"{offer.architect.display_name} taklifingizni rad etdi: {application.location}."
        + (" E'lonni boshqa arxitektorga yuborishingiz yoki hammaga ochishingiz mumkin." if freed else ""),
        reverse("applications:detail", args=[offer.application_id]),
    )
    if freed:   # the order goes back to "not sent yet" so its owner can choose again
        application.publication = Application.Publication.DRAFT
        application.sent_to = None
        application.save(update_fields=["publication", "sent_to"])
    offer.delete()


@transaction.atomic
def reject_offer(offer: Offer) -> None:
    offer.status = Offer.Status.REJECTED
    offer.decided_at = timezone.now()
    offer.save(update_fields=["status", "decided_at"])
    place = offer.application.location
    if offer.source == Offer.Source.ARCHITECT_APPLIED:      # the client turned the architect down
        notify(offer.architect, f"Arizangiz rad etildi: {place}.", dashboard_url(offer.architect, "orders"))
    else:                                                    # the architect declined the client's invitation
        notify(
            offer.application.owner, f"{offer.architect.display_name} taklifingizni rad etdi: {place}.",
            reverse("applications:detail", args=[offer.application_id]),
        )


@transaction.atomic
def finish_by_architect(offer: Offer) -> None:
    """The architect (or studio) presses "Yakunlash": the job is over and moves to finished
    projects. A studio's assignment is closed too."""
    assignment = getattr(offer, "studio_assignment", None)
    if assignment is not None and assignment.status != StudioAssignment.Status.DONE:
        assignment.status = StudioAssignment.Status.DONE
        assignment.done_at = timezone.now()
        assignment.save(update_fields=["status", "done_at"])
    complete_offer(offer, by_architect=True)


@transaction.atomic
def complete_offer(offer: Offer, by_architect: bool = False) -> None:
    offer.status = Offer.Status.COMPLETED
    offer.completed_at = timezone.now()
    offer.save(update_fields=["status", "completed_at"])

    offer.application.status = Application.Status.CLOSED
    offer.application.save(update_fields=["status"])

    architect = offer.architect
    architect.completed_projects_count += 1
    architect.save(update_fields=["completed_projects_count"])
    if by_architect:
        notify(
            offer.application.owner, f"{architect.display_name} loyihani yakunladi: {offer.application.location}.",
            reverse("applications:detail", args=[offer.application_id]),
        )
    else:
        notify(
            architect, f"Mijoz loyihani yakunlandi deb belgiladi: {offer.application.location}.",
            dashboard_url(architect, "finished"),
        )


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
    previous = assignment.worker
    assignment.worker = worker
    assignment.status = StudioAssignment.Status.ASSIGNED
    assignment.assigned_at = timezone.now()
    assignment.overdue_notified_at = None
    fields = ["worker", "status", "assigned_at", "overdue_notified_at"]
    if deadline is not None:
        assignment.deadline = deadline
        fields.append("deadline")
    assignment.save(update_fields=fields)
    place = assignment.offer.application.location
    when = f" Muddat: {_day(assignment.deadline)}." if assignment.deadline else ""
    notify(worker, f"Sizga buyurtma biriktirildi: {place}.{when}", dashboard_url(worker, "tasks"))
    if previous is not None and previous.pk != worker.pk:
        # The job leaves the previous worker's list; they are told why.
        notify(previous, f"Buyurtma boshqa xodimga berildi: {place}.", dashboard_url(previous, "tasks"))


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
    notify(
        assignment.offer.architect, f"{worker} buyurtmani oldi: {assignment.offer.application.location}.",
        dashboard_url(assignment.offer.architect, "orders"),
    )


@transaction.atomic
def set_deadline(assignment: StudioAssignment, deadline) -> None:
    assignment.deadline = deadline
    assignment.overdue_notified_at = None
    assignment.save(update_fields=["deadline", "overdue_notified_at"])
    if assignment.worker and deadline:
        notify(
            assignment.worker,
            f"Buyurtma muddati belgilandi: {assignment.offer.application.location} — {_day(deadline)}.",
            dashboard_url(assignment.worker, "tasks"),
        )


@transaction.atomic
def mark_assignment_done(assignment: StudioAssignment) -> None:
    assignment.status = StudioAssignment.Status.DONE
    assignment.done_at = timezone.now()
    assignment.save(update_fields=["status", "done_at"])
    if assignment.worker:
        notify(
            assignment.offer.architect, f"{assignment.worker} buyurtmani bajardi: {assignment.offer.application.location}.",
            dashboard_url(assignment.offer.architect, "orders"),
        )


@transaction.atomic
def notify_overdue_assignments(user=None) -> int:
    """Tell the studio and the worker when a worker missed a deadline (once per deadline).

    There is no background clock, so this runs whenever someone concerned opens a page (and from
    the ``notify_overdue`` command, for a cron job). ``user`` limits it to that person's jobs."""
    late = StudioAssignment.objects.filter(
        status=StudioAssignment.Status.ASSIGNED, deadline__lt=timezone.localdate(), overdue_notified_at__isnull=True,
        worker__isnull=False,
    ).select_related("offer__application", "offer__architect__user", "worker__user")
    if user is not None:
        late = late.filter(Q(offer__architect__user=user) | Q(worker__user=user))
    count = 0
    for assignment in late:
        place = assignment.offer.application.location
        when = _day(assignment.deadline)
        notify(
            assignment.offer.architect, f"{assignment.worker} muddatni o'tkazib yubordi: {place} (muddat: {when}).",
            dashboard_url(assignment.offer.architect, "orders"),
        )
        notify(assignment.worker, f"Muddat o'tib ketdi: {place} (muddat: {when}). Ishni tugating.", dashboard_url(assignment.worker, "tasks"))
        assignment.overdue_notified_at = timezone.now()
        assignment.save(update_fields=["overdue_notified_at"])
        count += 1
    return count
