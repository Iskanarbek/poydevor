from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from applications.models import Application
from architects.models import ArchitectProfile
from architects.navigation import dashboard_url, portfolio_url
from offers.models import Offer
from offers.services import (
    ArchitectNotAllowedError,
    MaxArchitectsReachedError,
    MAX_ACTIVE_OFFERS_PER_APPLICATION,
    INVITE_ACCEPT_COST,
    OFFER_COST,
    OfferAlreadyDecidedError,
    accept_invitation,
    accept_offer,
    complete_offer,
    decline_invitation,
    finish_by_architect,
    reject_offer,
    send_offer,
)
from wallet.models import Wallet
from wallet.services import InsufficientCoinsError


PORTFOLIO_MESSAGE = (
    "Portfolio to'ldirilmaguncha e'lonlarda qatnasha olmaysiz va takliflarni qabul qila olmaysiz. "
    "Avval kerakli loyihalar va rasmlarni qo'shing."
)
VERIFICATION_MESSAGE = (
    "Portfolioingiz hali administrator tomonidan tasdiqlanmagan. 48 soat ichida ko'rib chiqiladi — "
    "tasdiqlangach e'lonlarda qatnasha olasiz va takliflarni qabul qila olasiz."
)


def _portfolio_gate_message(architect):
    if not architect.portfolio_ok:
        return PORTFOLIO_MESSAGE
    if not architect.verification_ok:
        return VERIFICATION_MESSAGE
    return None


@login_required
def send_from_architect_profile(request, architect_pk):
    architect = get_object_or_404(ArchitectProfile.objects.public(), pk=architect_pk)
    user_applications = request.user.applications.filter(status=Application.Status.OPEN)
    error = None
    if request.method == "POST":
        application = get_object_or_404(user_applications, pk=request.POST.get("application"))
        try:
            send_offer(application, architect, source=Offer.Source.USER_INVITED)
            return redirect("applications:detail", pk=application.pk)
        except (MaxArchitectsReachedError, ArchitectNotAllowedError) as e:
            error = str(e)
    return render(request, "offers/send_form.html", {
        "architect": architect, "applications": user_applications, "error": error,
    })


@login_required
def architect_apply(request, application_pk):
    """GET shows an open project in full so an architect can judge whether it
    suits them; POST takes it, spending the coins."""
    application = get_object_or_404(
        Application.objects.select_related("interior_style"), pk=application_pk, status=Application.Status.OPEN,
    )
    architect = get_object_or_404(ArchitectProfile.objects.takers(), user=request.user)
    gate_message = _portfolio_gate_message(architect)
    if gate_message:
        messages.warning(request, gate_message)
        return redirect(portfolio_url(architect))
    wallet, _ = Wallet.objects.get_or_create(architect=architect)
    if request.method == "POST":
        try:
            send_offer(application, architect, source=Offer.Source.ARCHITECT_APPLIED)
        except (MaxArchitectsReachedError, InsufficientCoinsError, ArchitectNotAllowedError) as e:
            return render(request, "offers/apply_error.html", {"error": str(e), "application": application})
        except IntegrityError:
            # Double-submit: this architect already has a pending offer on this application
            # (hits the partial unique constraint) — treat it the same as the max-reached case.
            return render(request, "offers/apply_error.html", {
                "error": "Siz bu e'longa allaqachon ariza yubordingiz.", "application": application,
            })
        return redirect(dashboard_url(architect, "orders"))

    slots_taken = application.offers.filter(status=Offer.Status.PENDING).count()
    return render(request, "offers/architect_apply_confirm.html", {
        "application": application,
        "offer_cost": OFFER_COST,
        "wallet": wallet,
        "can_afford": wallet.balance >= OFFER_COST,
        "balance_after": wallet.balance - OFFER_COST,
        "slots_taken": slots_taken,
        "max_slots": MAX_ACTIVE_OFFERS_PER_APPLICATION,
        "slot_range": range(1, MAX_ACTIVE_OFFERS_PER_APPLICATION + 1),
        "is_full": slots_taken >= MAX_ACTIVE_OFFERS_PER_APPLICATION,
        "already_applied": application.offers.filter(
            architect=architect, status__in=[Offer.Status.PENDING, Offer.Status.ACCEPTED],
        ).exists(),
        "store_url": dashboard_url(architect, "store"),
        "back_url": dashboard_url(architect, "market"),
    })


@login_required
def respond(request, offer_pk):
    offer = get_object_or_404(Offer, pk=offer_pk, architect__user=request.user, status=Offer.Status.PENDING)
    if request.method == "POST":
        if request.POST.get("decision") == "accept":
            if not offer.architect.can_take_offers:
                messages.warning(request, _portfolio_gate_message(offer.architect) or PORTFOLIO_MESSAGE)
                return redirect(portfolio_url(offer.architect))
            try:
                if offer.source == Offer.Source.USER_INVITED:
                    accept_invitation(offer)
                else:
                    accept_offer(offer)
                messages.success(request, "Buyurtma qabul qilindi. Endi xodim tanlang.")
            except InsufficientCoinsError:
                messages.warning(
                    request,
                    f"Taklifni qabul qilish uchun {INVITE_ACCEPT_COST} tanga kerak. Avval tanga sotib oling.",
                )
                return redirect(dashboard_url(offer.architect, "store"))
            except OfferAlreadyDecidedError:
                return redirect(dashboard_url(offer.architect, "orders"))
        else:
            architect = offer.architect
            decline_invitation(offer)
            messages.success(request, "Taklif rad etildi va jadvaldan olib tashlandi.")
            return redirect(dashboard_url(architect, "orders"))
    return redirect(dashboard_url(offer.architect, "orders"))


@login_required
def user_respond(request, offer_pk):
    offer = get_object_or_404(
        Offer, pk=offer_pk, application__owner=request.user, status=Offer.Status.PENDING,
    )
    if request.method == "POST":
        if request.POST.get("decision") == "accept":
            try:
                accept_offer(offer)
            except OfferAlreadyDecidedError:
                return redirect("applications:detail", pk=offer.application.pk)
        else:
            reject_offer(offer)
    return redirect("applications:detail", pk=offer.application.pk)


@login_required
def mark_complete(request, offer_pk):
    offer = get_object_or_404(
        Offer, pk=offer_pk, application__owner=request.user, status=Offer.Status.ACCEPTED,
    )
    if request.method == "POST":
        complete_offer(offer)
    return redirect("applications:detail", pk=offer.application.pk)


@login_required
def architect_finish(request, offer_pk):
    """"Yakunlash" in the architect's (or studio's) table: the job is finished and moves to
    the finished projects."""
    offer = get_object_or_404(Offer, pk=offer_pk, architect__user=request.user, status=Offer.Status.ACCEPTED)
    if request.method == "POST":
        finish_by_architect(offer)
        messages.success(request, "Loyiha yakunlandi va «Tugatilgan ishlar»ga o'tdi.")
        return redirect(dashboard_url(offer.architect, "orders"))      # stay on the Buyurtmalar page
    return redirect(dashboard_url(offer.architect, "orders"))


@login_required
def offer_detail(request, offer_pk):
    """Everything about one project, for the architect/studio it belongs to and for the worker
    it is assigned to. The client's contact is shown only once the offer was accepted."""
    offer = get_object_or_404(
        Offer.objects.select_related("application", "application__owner", "application__interior_style", "architect__user"),
        pk=offer_pk,
    )
    assignment = getattr(offer, "studio_assignment", None)
    is_owner = offer.architect.user_id == request.user.id
    is_worker = bool(assignment and assignment.worker_id and assignment.worker.user_id == request.user.id)
    if not (is_owner or is_worker):
        raise Http404
    profile = offer.architect if is_owner else assignment.worker
    if is_worker:
        back_url = dashboard_url(profile, "tasks")
    else:
        back_url = dashboard_url(profile, "orders")
    return render(request, "offers/offer_detail.html", {
        "offer": offer,
        "application": offer.application,
        "assignment": assignment,
        "is_owner": is_owner,
        "is_worker": is_worker,
        "show_contact": offer.status in (Offer.Status.ACCEPTED, Offer.Status.COMPLETED),
        "back_url": back_url,
    })
