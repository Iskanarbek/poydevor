"""A small, site-styled panel for staff — not Django admin's generic UI.

Login is separate from the ordinary site login on purpose: the normal
accounts:login form signs people in with just a phone number (no password),
which is fine for clients and architects but would be a serious hole for
staff accounts — anyone who knew a staff member's phone number could sign in
as them. So staff always authenticate with phone *and* password here, through
Django's own AuthenticationForm (it already adapts to our USERNAME_FIELD).

Freeze/unfreeze reuses the views already registered in accounts/admin.py
(same permission check, same behaviour) — no need to duplicate them here.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from architects.models import ArchitectProfile
from architects.services import decide_verification, set_approval

Kind = ArchitectProfile.Kind
Approval = ArchitectProfile.ApprovalStatus
Verification = ArchitectProfile.VerificationStatus


def staff_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect(f"{reverse('staff_login')}?next={request.path}")
        return view_func(request, *args, **kwargs)

    return wrapper


def staff_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("staff_home")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if not user.is_staff:
            form.add_error(None, "Bu hisobda admin panelga kirish huquqi yo'q.")
        else:
            auth_login(request, user)
            return redirect(request.GET.get("next") or "staff_home")
    return render(request, "staff_panel/login.html", {"form": form})


@staff_required
def staff_home(request):
    counts = {
        "pending_verification": ArchitectProfile.objects.filter(
            portfolio_verification=Verification.PENDING,
        ).count(),
        "pending_registration": ArchitectProfile.objects.filter(approval_status=Approval.PENDING).count(),
        "total_architects": ArchitectProfile.objects.count(),
    }
    return render(request, "staff_panel/home.html", {"counts": counts})


@staff_required
def architects_list(request):
    qs = ArchitectProfile.objects.select_related("user", "studio").annotate(
        project_count=Count("projects", distinct=True),
    ).order_by("-created_at")

    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(user__phone__icontains=q),
        )
    kind = request.GET.get("kind", "")
    if kind:
        qs = qs.filter(kind=kind)
    verification = request.GET.get("verification", "")
    if verification:
        qs = qs.filter(portfolio_verification=verification)
    account = request.GET.get("account", "")
    if account == "frozen":
        qs = qs.filter(user__is_active=False)
    elif account == "active":
        qs = qs.filter(user__is_active=True)

    return render(request, "staff_panel/architects_list.html", {
        "architects": qs[:300],
        "q": q, "kind": kind, "verification": verification, "account": account,
        "kinds": Kind.choices, "verifications": Verification.choices,
    })


@staff_required
def architect_detail(request, pk):
    profile = get_object_or_404(
        ArchitectProfile.objects.select_related("user", "studio").prefetch_related("projects__images"), pk=pk,
    )
    return render(request, "staff_panel/architect_detail.html", {"profile": profile})


@require_POST
@staff_required
def architect_verify(request, pk):
    profile = get_object_or_404(ArchitectProfile, pk=pk)
    decide_verification(profile, Verification.VERIFIED)
    messages.success(request, "Portfolio tasdiqlandi.")
    return redirect("staff_architect_detail", pk=pk)


@require_POST
@staff_required
def architect_reject(request, pk):
    profile = get_object_or_404(ArchitectProfile, pk=pk)
    decide_verification(profile, Verification.REJECTED, request.POST.get("note", "").strip())
    messages.warning(request, "Portfolio rad etildi.")
    return redirect("staff_architect_detail", pk=pk)


@require_POST
@staff_required
def architect_approve_registration(request, pk):
    profile = get_object_or_404(ArchitectProfile, pk=pk, approval_status=Approval.PENDING)
    set_approval(profile, Approval.APPROVED)
    messages.success(request, "Ro'yxatdan o'tish tasdiqlandi.")
    return redirect("staff_architect_detail", pk=pk)


@require_POST
@staff_required
def architect_reject_registration(request, pk):
    profile = get_object_or_404(ArchitectProfile, pk=pk, approval_status=Approval.PENDING)
    set_approval(profile, Approval.REJECTED)
    messages.warning(request, "Ro'yxatdan o'tish rad etildi.")
    return redirect("staff_architect_detail", pk=pk)
