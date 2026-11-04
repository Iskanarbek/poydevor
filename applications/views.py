from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from applications.forms import ApplicationForm
from architects.gallery import gallery_context
from applications.models import Application
from applications.pricing import estimate_price
from applications.services import (
    delete_application as delete_order,
    live_offers,
)

Status = Application.Status


@login_required
def price_estimate(request):
    """The live "taxminiy narx" under the posting form: answers with the range for the numbers
    typed so far (or says what is still missing)."""
    g = request.GET
    estimate = estimate_price(g.get("size"), g.get("object_type"), g.get("service_type"), g.get("rooms"), g.get("location", ""))
    if estimate is None:
        return JsonResponse({"ok": False})
    return JsonResponse({"ok": True, "min": estimate[0], "max": estimate[1]})


@login_required
def post_application(request):
    if request.method == "POST":
        form = ApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            application = form.save(commit=False)
            application.owner = request.user
            application.save()
            messages.success(request, "E'loningiz joylandi! Arxitektorlar tez orada ariza yuborishadi.")
            return redirect("applications:dashboard")
    else:
        form = ApplicationForm()
    return render(request, "applications/post_form.html", {
        "form": form,
    })


@login_required
def dashboard(request):
    applications = request.user.applications.visible()
    return render(request, "applications/dashboard.html", {
        **gallery_context(request),
        "applications": applications,
    })


@login_required
def detail(request, pk):
    application = get_object_or_404(Application, pk=pk, owner=request.user, deleted_at__isnull=True)
    return render(request, "applications/detail.html", {
        "application": application,
        "offers": application.offers.select_related("architect__user", "architect__studio_owned", "review")
        .prefetch_related("architect__skills", "architect__projects__images"),
    })


@login_required
def delete_application(request, pk):
    """Deleting an order asks first (GET shows what will happen), then a POST does it."""
    application = get_object_or_404(Application, pk=pk, owner=request.user, deleted_at__isnull=True)
    if request.method == "POST":
        delete_order(application)
        return redirect("applications:dashboard")
    offers = live_offers(application)
    return render(request, "applications/confirm_delete.html", {
        "application": application,
        "refund_count": offers.filter(source="architect_applied").count(),
        "live_count": offers.count(),
        "in_progress": application.status == Status.IN_PROGRESS,
        "finished": application.status == Status.CLOSED,
    })
