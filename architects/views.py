from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from architects.forms import ArchitectProfileForm, PortfolioImageForm, PortfolioProjectForm
from architects.models import ArchitectProfile, Style


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
        form = ArchitectProfileForm(request.POST, request.FILES)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            form.save_m2m()
            return redirect("architects:dashboard")
    else:
        form = ArchitectProfileForm()
    return render(request, "architects/onboarding.html", {"form": form})


@architect_required
def dashboard(request):
    profile = get_object_or_404(ArchitectProfile, user=request.user)
    return render(request, "architects/dashboard.html", {"profile": profile})


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
