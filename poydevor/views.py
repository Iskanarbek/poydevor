import hmac
import io
import os

from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("accounts:welcome")


@login_required
def dashboard_redirect(request):
    if request.user.role == request.user.Role.ARCHITECT:
        return redirect("architects:dashboard")
    return redirect("applications:dashboard")


def internal_setup(request):
    """One-off endpoint to run migrate + seed_lookups against whatever
    database/storage this deployment is actually configured with.

    Exists because Vercel marks DATABASE_URL/BLOB_READ_WRITE_TOKEN as
    "Sensitive" (write-only in the dashboard — can't be read back to run
    these commands locally), but the deployed app itself has them at
    runtime. Gated behind a secret token so it can't be triggered by
    anyone else; intended to be removed once initial setup is done.
    """
    expected_token = os.environ.get("SETUP_TOKEN")
    if not expected_token or request.GET.get("token") != expected_token:
        return HttpResponseForbidden("Forbidden")

    output = io.StringIO()
    try:
        call_command("migrate", stdout=output, stderr=output)
    except Exception as exc:
        output.write(f"\nmigrate FAILED: {exc}\n")
        return HttpResponse(output.getvalue(), content_type="text/plain")

    try:
        call_command("seed_lookups", stdout=output, stderr=output)
    except Exception as exc:
        output.write(f"\nseed_lookups FAILED: {exc}\n")

    return HttpResponse(output.getvalue(), content_type="text/plain")


def internal_expire_orders(request):
    """Daily clean-up hook (point a cron job here): deletes expired orders and
    refunds the architects. Protected by CRON_SECRET, sent either as
    ``Authorization: Bearer <secret>`` (what Vercel Cron sends) or as ``?token=``.
    Disabled while CRON_SECRET is not set."""
    from django.conf import settings
    from applications.services import expire_stale_applications

    secret = settings.CRON_SECRET
    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip() or request.GET.get("token", "")
    if not secret or not hmac.compare_digest(given.encode(), secret.encode()):
        return HttpResponseForbidden("Forbidden")
    return HttpResponse(f"removed: {expire_stale_applications()}\n", content_type="text/plain")
