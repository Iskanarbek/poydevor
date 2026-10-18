from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from applications.forms import ApplicationForm
from applications.models import Application
from applications.services import (
    delete_application as delete_order,
    expire_stale_applications,
    live_offers,
    renew_application,
)

Status = Application.Status


@login_required
def post_application(request):
    if request.method == "POST":
        form = ApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            application = form.save(commit=False)
            application.owner = request.user
            application.save()
            return redirect("applications:detail", pk=application.pk)
    else:
        form = ApplicationForm()
    return render(request, "applications/post_form.html", {
        "form": form,
        "lifetime_days": settings.ORDER_LIFETIME_DAYS,
        "renew_after_days": settings.ORDER_RENEW_AFTER_DAYS,
    })


@login_required
def dashboard(request):
    expire_stale_applications()
    applications = request.user.applications.visible()
    recently_expired = request.user.applications.filter(
        auto_deleted=True, deleted_at__gte=timezone.now() - timedelta(days=30),
    )
    return render(request, "applications/dashboard.html", {
        "applications": applications,
        "recently_expired": recently_expired,
        "lifetime_days": settings.ORDER_LIFETIME_DAYS,
        "renew_after_days": settings.ORDER_RENEW_AFTER_DAYS,
    })


@login_required
def detail(request, pk):
    expire_stale_applications()
    application = get_object_or_404(Application, pk=pk, owner=request.user, deleted_at__isnull=True)
    return render(request, "applications/detail.html", {
        "application": application,
        "offers": application.offers.select_related("architect__user", "architect__studio_owned", "review")
        .prefetch_related("architect__skills", "architect__projects__images"),
        "lifetime_days": settings.ORDER_LIFETIME_DAYS,
        "renew_after_days": settings.ORDER_RENEW_AFTER_DAYS,
    })


@login_required
@require_POST
def renew(request, pk):
    """"Hali ham izlayapman": the owner confirms the order is still wanted."""
    application = get_object_or_404(Application, pk=pk, owner=request.user, deleted_at__isnull=True)
    if not renew_application(application) and application.status == Status.OPEN:
        messages.warning(request, f"Tasdiqlash tugmasi {application.days_until_renew} kundan keyin ochiladi.")
    if request.POST.get("back") == "dashboard":
        return redirect("applications:dashboard")
    return redirect("applications:detail", pk=application.pk)


@login_required
def delete_application(request, pk):
    """Deleting an order asks first (GET shows what will happen), then a POST does it."""
    expire_stale_applications()
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
