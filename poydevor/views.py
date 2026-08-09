import io
import os

from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("architects:list")


@login_required
def dashboard_redirect(request):
    if request.user.role == request.user.Role.ARCHITECT:
        return redirect("architects:dashboard")
    return redirect("applications:dashboard")


def internal_setup(request):
    """One-off endpoint to run migrate + seed_demo_data against whatever
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
        call_command("seed_demo_data", stdout=output, stderr=output)
    except Exception as exc:
        output.write(f"\nseed_demo_data FAILED: {exc}\n")

    return HttpResponse(output.getvalue(), content_type="text/plain")
