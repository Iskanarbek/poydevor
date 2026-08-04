from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render

from applications.models import Application
from architects.forms import (
    ArchitectOnboardingForm,
    ArchitectProfileForm,
    PortfolioImageForm,
    PortfolioProjectForm,
)
from architects.models import ArchitectProfile, Style
from offers.models import Offer
from offers.services import MAX_ACTIVE_OFFERS_PER_APPLICATION
from wallet.models import Wallet


def architect_required(view_func):
    """Restrict a view to logged-in users with the architect role.

    Non-architect users are redirected to the role-aware ``dashboard``
    stub, which routes them to the area appropriate for their role.
    """

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role != request.user.Role.ARCHITECT:
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)

    return wrapper


@architect_required
def onboarding(request):
    if hasattr(request.user, "architect_profile"):
        return redirect("architects:dashboard")
    if request.method == "POST":
        form = ArchitectOnboardingForm(request.POST, request.FILES)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            Wallet.objects.create(architect=profile)
            form.save_m2m()
            return redirect("architects:dashboard")
    else:
        form = ArchitectOnboardingForm()
    return render(request, "architects/onboarding.html", {"form": form})


@architect_required
def dashboard(request):
    profile = get_object_or_404(ArchitectProfile, user=request.user)
    open_applications = Application.objects.filter(status=Application.Status.OPEN).annotate(
        pending_offers_count=Count("offers", filter=Q(offers__status=Offer.Status.PENDING)),
    )
    # Broader than the DB's partial unique constraint (which only blocks a second
    # PENDING offer): an accepted offer is included here too so the "already
    # applied" UI state also covers applications this architect has already won.
    already_applied_application_ids = set(
        Offer.objects.filter(
            architect=profile,
            application__status=Application.Status.OPEN,
            status__in=[Offer.Status.PENDING, Offer.Status.ACCEPTED],
        ).values_list("application_id", flat=True)
    )
    return render(request, "architects/dashboard.html", {
        "profile": profile,
        "open_applications": open_applications,
        "already_applied_application_ids": already_applied_application_ids,
        "max_active_offers": MAX_ACTIVE_OFFERS_PER_APPLICATION,
        "offer_slot_range": range(1, MAX_ACTIVE_OFFERS_PER_APPLICATION + 1),
    })


@architect_required
def portfolio_edit(request):
    profile = get_object_or_404(ArchitectProfile, user=request.user)
    if request.method == "POST":
        form = ArchitectProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("architects:dashboard")
    else:
        form = ArchitectProfileForm(instance=profile)
    return render(request, "architects/portfolio_form.html", {"form": form, "profile": profile})


@architect_required
def project_create(request):
    profile = get_object_or_404(ArchitectProfile, user=request.user)
    if request.method == "POST":
        form = PortfolioProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.architect = profile
            project.order = (profile.projects.aggregate(Max("order"))["order__max"] or 0) + 1
            project.save()
            return redirect("architects:dashboard")
    else:
        form = PortfolioProjectForm()
    return render(request, "architects/project_form.html", {"form": form})


@architect_required
def project_image_add(request, project_id):
    profile = get_object_or_404(ArchitectProfile, user=request.user)
    project = get_object_or_404(profile.projects, id=project_id)
    if request.method == "POST":
        form = PortfolioImageForm(request.POST, request.FILES)
        if form.is_valid():
            image = form.save(commit=False)
            image.project = project
            image.order = (project.images.aggregate(Max("order"))["order__max"] or 0) + 1
            image.save()
            return redirect("architects:dashboard")
    else:
        form = PortfolioImageForm()
    return render(request, "architects/project_image_form.html", {"form": form, "project": project})


def public_list(request):
    profiles = ArchitectProfile.objects.all().prefetch_related("projects__images", "styles")
    style_id = request.GET.get("style")
    if style_id:
        profiles = profiles.filter(styles__id=style_id).distinct()
    styles = Style.objects.all()
    return render(request, "architects/public_list.html", {"profiles": profiles, "styles": styles, "selected_style": style_id})


def public_detail(request, pk):
    profile = get_object_or_404(ArchitectProfile.objects.prefetch_related("projects__images", "styles", "skills"), pk=pk)
    style_id = request.GET.get("style")
    projects = profile.projects.all()
    if style_id:
        projects = projects.filter(style_id=style_id)
    # Filtering drops the prefetch cache populated by the profile queryset's
    # `prefetch_related("projects__images", ...)`, so re-prefetch images
    # explicitly on the (possibly filtered) queryset to avoid N+1 queries
    # in the template's `project.images.all()` loop. select_related("style")
    # likewise avoids a per-project query for the template's `project.style`
    # access.
    projects = projects.select_related("style").prefetch_related("images")
    return render(request, "architects/public_detail.html", {"profile": profile, "projects": projects, "selected_style": style_id})
