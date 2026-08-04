from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from applications.models import Application
from architects.models import ArchitectProfile
from offers.models import Offer
from offers.services import (
    MaxArchitectsReachedError,
    accept_offer,
    complete_offer,
    reject_offer,
    send_offer,
)
from wallet.services import InsufficientCoinsError


@login_required
def send_from_architect_profile(request, architect_pk):
    architect = get_object_or_404(ArchitectProfile, pk=architect_pk)
    user_applications = request.user.applications.filter(status=Application.Status.OPEN)
    error = None
    if request.method == "POST":
        application = get_object_or_404(user_applications, pk=request.POST.get("application"))
        try:
            send_offer(application, architect, source=Offer.Source.USER_INVITED)
            return redirect("applications:detail", pk=application.pk)
        except MaxArchitectsReachedError as e:
            error = str(e)
    return render(request, "offers/send_form.html", {
        "architect": architect, "applications": user_applications, "error": error,
    })


@login_required
def architect_apply(request, application_pk):
    application = get_object_or_404(Application, pk=application_pk, status=Application.Status.OPEN)
    architect = get_object_or_404(ArchitectProfile, user=request.user)
    try:
        send_offer(application, architect, source=Offer.Source.ARCHITECT_APPLIED)
    except (MaxArchitectsReachedError, InsufficientCoinsError) as e:
        return render(request, "offers/apply_error.html", {"error": str(e), "application": application})
    except IntegrityError:
        # Double-submit: this architect already has a pending offer on this application
        # (hits the partial unique constraint) — treat it the same as the max-reached case.
        return render(request, "offers/apply_error.html", {
            "error": "Siz bu e'longa allaqachon ariza yubordingiz.", "application": application,
        })
    return redirect("architects:dashboard")


@login_required
def respond(request, offer_pk):
    offer = get_object_or_404(Offer, pk=offer_pk, architect__user=request.user, status=Offer.Status.PENDING)
    if request.method == "POST":
        if request.POST.get("decision") == "accept":
            accept_offer(offer)
        else:
            reject_offer(offer)
    return redirect("architects:dashboard")


@login_required
def user_respond(request, offer_pk):
    offer = get_object_or_404(
        Offer, pk=offer_pk, application__owner=request.user, status=Offer.Status.PENDING,
    )
    if request.method == "POST":
        if request.POST.get("decision") == "accept":
            accept_offer(offer)
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
