from datetime import date
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.views import login_without_password
from applications.models import Application
from applications.services import expire_stale_applications
from architects.forms import (
    ArchitectProfileForm,
    EmployeeRegistrationForm,
    FreelancerRegistrationForm,
    PortfolioImagesForm,
    PortfolioProjectEditForm,
    PortfolioProjectForm,
    StudioRegistrationForm,
)
from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject, Style
from architects.navigation import dashboard_url, portfolio_url
from architects.services import register_employee, register_freelancer, register_studio, set_approval
from offers.models import Offer, StudioAssignment
from offers.services import (
    MAX_ACTIVE_OFFERS_PER_APPLICATION,
    AssignmentAlreadyTakenError,
    WorkerNotInStudioError,
    assign_worker,
    claim_assignment,
    mark_assignment_done,
    set_deadline,
)
from wallet.payments.config import enabled_providers
from wallet.services import coin_packages

Kind = ArchitectProfile.Kind
Approval = ArchitectProfile.ApprovalStatus

STUDIO_TABS = [
    ("employees", "Xodimlar ro'yxati"),
    ("orders", "Buyurtmalar taqsimoti"),
    ("finished", "Tugatilgan ishlar"),
    ("ongoing", "Davom etayotgan ishlar"),
    ("market", "E'lonlar bozori"),
    ("room", "Mening xonam"),
    ("store", "Store"),
]
FREELANCER_TABS = [
    ("market", "E'lonlar bozori"),
    ("room", "Mening xonam"),
    ("finished", "Tugallangan loyihalar"),
    ("store", "Store"),
]
# A studio employee's panel: same layout as the studio and freelancer ones. The labels
# get a count appended in employee_workspace().
EMPLOYEE_TABS = [
    ("tasks", "Mening ishlarim"),
    ("open", "Ochiq buyurtmalar"),
    ("done", "Bajarilgan ishlar"),
    ("studio", "Studiya"),
]


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


def approved_architect_required(*kinds):
    """Restrict a view to *approved* architects of the given kinds.

    Everyone else is sent to the right place: to registration if they have no
    profile yet, to the status screen while their application is pending or
    rejected, and to their own dashboard if they are the wrong kind.
    """

    def decorator(view_func):
        @wraps(view_func)
        @architect_required
        def wrapper(request, *args, **kwargs):
            profile = getattr(request.user, "architect_profile", None)
            if profile is None:
                return redirect("architects:select_type")
            if profile.approval_status != Approval.APPROVED:
                return redirect("architects:register_status")
            if profile.kind not in kinds:
                return redirect(dashboard_url(profile))
            request.architect_profile = profile
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def portfolio_builder_required(view_func):
    """Studios and freelancers build their portfolio right after signing up, even
    while their application is still being reviewed."""

    @wraps(view_func)
    @architect_required
    def wrapper(request, *args, **kwargs):
        profile = getattr(request.user, "architect_profile", None)
        if profile is None:
            return redirect("architects:select_type")
        if profile.kind == Kind.STUDIO_EMPLOYEE:
            return redirect(dashboard_url(profile))
        if profile.approval_status == Approval.REJECTED:
            return redirect("architects:register_status")
        request.architect_profile = profile
        return view_func(request, *args, **kwargs)

    return wrapper


# --- Registration ----------------------------------------------------------


def _registration_user(request):
    """The signed-in architect (without a profile yet) a registration attaches
    to, or None for a visitor who needs a new account. Returns a redirect
    response when this visitor shouldn't be registering at all."""
    if not request.user.is_authenticated:
        return None, None
    if request.user.role != request.user.Role.ARCHITECT:
        return None, redirect("dashboard")
    if hasattr(request.user, "architect_profile"):
        return None, redirect("architects:dashboard")
    return request.user, None


def select_type(request):
    _, early = _registration_user(request)
    if early is not None:
        return early
    return render(request, "architects/select_type.html")


def _register(request, form_class, template, save):
    user, early = _registration_user(request)
    if early is not None:
        return early
    if request.method == "POST":
        form = form_class(request.POST, request.FILES, user=user)
        if form.is_valid():
            profile = save(form.cleaned_data, user)
            if form.cleaned_data.get("avatar"):
                profile.avatar = form.cleaned_data["avatar"]
                profile.save(update_fields=["avatar"])
            if user is None:
                login_without_password(request, profile.user)
            # Studios and freelancers go straight into their account (where they are asked to build
            # their portfolio); employees wait for their studio owner on the status screen.
            if profile.approval_status == Approval.APPROVED:
                return redirect(dashboard_url(profile))
            return redirect("architects:register_status")
    else:
        form = form_class(user=user)
    return render(request, template, {"form": form})


def register_studio_view(request):
    return _register(
        request, StudioRegistrationForm, "architects/register_studio.html",
        lambda data, user: register_studio(data, user),
    )


def register_employee_view(request):
    return _register(
        request, EmployeeRegistrationForm, "architects/register_employee.html",
        lambda data, user: register_employee(data, user),
    )


def register_freelancer_view(request):
    return _register(
        request, FreelancerRegistrationForm, "architects/register_freelancer.html",
        lambda data, user: register_freelancer(data, user),
    )


@architect_required
def register_status(request):
    profile = getattr(request.user, "architect_profile", None)
    if profile is None:
        return redirect("architects:select_type")
    if profile.approval_status == Approval.APPROVED:
        return redirect(dashboard_url(profile))
    return render(request, "architects/register_status.html", {"profile": profile})


# --- Dashboards ------------------------------------------------------------


@architect_required
def dashboard(request):
    """Send an architect to whichever screen fits their current state."""
    profile = getattr(request.user, "architect_profile", None)
    if profile is None:
        return redirect("architects:select_type")
    if profile.approval_status != Approval.APPROVED:
        return redirect("architects:register_status")
    return redirect(dashboard_url(profile))


def _offers(profile, *statuses):
    return (
        profile.offers.filter(status__in=statuses)
        .select_related("application", "application__owner")
        .order_by("-created_at")
    )


def _market_context(profile):
    open_applications = Application.objects.filter(status=Application.Status.OPEN).select_related("interior_style").annotate(
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
    return {
        "open_applications": open_applications,
        "already_applied_application_ids": already_applied_application_ids,
        "max_active_offers": MAX_ACTIVE_OFFERS_PER_APPLICATION,
        "offer_slot_range": range(1, MAX_ACTIVE_OFFERS_PER_APPLICATION + 1),
        "my_offers": profile.offers.select_related("application", "application__owner"),
    }


def _store_context(profile):
    wallet = getattr(profile, "wallet", None)
    return {
        "wallet": wallet,
        "packages": coin_packages(),
        "providers": enabled_providers(),
        "offer_cost": settings.OFFER_COST_COINS,
        "coin_price_uzs": settings.COIN_PRICE_UZS,
        "transactions": wallet.transactions.all()[:50] if wallet else [],
    }


def _workspace(request, profile, tabs, default_tab, title):
    expire_stale_applications()
    tab_keys = [key for key, _ in tabs]
    tab = request.GET.get("tab")
    if tab not in tab_keys:
        # Until the portfolio is finished, that is where the architect is sent.
        tab = default_tab if profile.portfolio_ok or profile.kind == Kind.STUDIO_EMPLOYEE else "room"
    context = {
        "profile": profile,
        "title": title,
        "tabs": tabs,
        "tab": tab,
        "tab_template": f"architects/tabs/_{tab}.html",
        "wallet": getattr(profile, "wallet", None),
        "offer_cost": settings.OFFER_COST_COINS,
        # Studios and freelancers must finish their portfolio before they can take orders.
        "portfolio_locked": not profile.portfolio_ok and profile.kind != Kind.STUDIO_EMPLOYEE,
    }
    wallet = context["wallet"]
    context["projects_left"] = wallet.balance // settings.OFFER_COST_COINS if wallet else 0
    if tab == "market":
        context.update(_market_context(profile))
        if context["portfolio_locked"]:
            context["open_applications"] = []
    elif tab == "store":
        context.update(_store_context(profile))
    elif tab == "room":
        context["projects"] = list(profile.projects.select_related("style").prefetch_related("images"))
        context["progress"] = profile.portfolio_progress(context["projects"])
    elif tab == "finished":
        context["offers"] = _offers(profile, Offer.Status.COMPLETED)
    elif tab == "ongoing":
        context["offers"] = _offers(profile, Offer.Status.ACCEPTED)
    elif tab == "employees":
        studio = profile.studio_owned
        context["studio"] = studio
        context["pending_employees"] = studio.employees.filter(approval_status=Approval.PENDING).select_related("user")
        context["employees"] = studio.employees.filter(approval_status=Approval.APPROVED).select_related("user")
    elif tab == "orders":
        studio = profile.studio_owned
        employees = list(studio.employees.filter(approval_status=Approval.APPROVED).select_related("user"))
        context["studio"] = studio
        context["employees"] = employees
        context["assignments"] = list(
            StudioAssignment.objects.filter(offer__architect=profile)
            .select_related("offer__application", "offer__application__owner", "worker__user")
            .order_by("-created_at")
        )
        context["worker_board"] = _worker_board(employees, context["assignments"])
    return render(request, "architects/workspace.html", context)


def _worker_board(employees, assignments):
    """One row per studio employee: their current (undone) assignment, if
    any, and whether it's overdue — what the studio owner scans to see who
    is busy, who skipped a deadline, and who is free for the next job."""
    active_by_worker = {}
    for a in assignments:
        if a.worker_id and a.status != StudioAssignment.Status.DONE:
            active_by_worker[a.worker_id] = a
    rows = []
    for employee in employees:
        current = active_by_worker.get(employee.id)
        rows.append({
            "employee": employee,
            "current": current,
            "available": current is None,
            "overdue": bool(current and current.is_overdue),
        })
    return rows


@approved_architect_required(Kind.STUDIO_OWNER)
def studio_dashboard(request):
    profile = request.architect_profile
    return _workspace(request, profile, STUDIO_TABS, "employees", profile.studio_owned.name)


@approved_architect_required(Kind.FREELANCER)
def freelancer_dashboard(request):
    profile = request.architect_profile
    return _workspace(request, profile, FREELANCER_TABS, "market", str(profile))


@approved_architect_required(Kind.STUDIO_EMPLOYEE)
def employee_workspace(request):
    """The employee's home: the same panel layout as a studio or freelancer gets, with
    their own jobs, the studio's open (unclaimed) orders, what they finished, and the studio."""
    profile = request.architect_profile
    studio = profile.studio
    open_assignments, my_assignments, my_done = [], [], []
    colleagues = []
    if studio is not None:
        assignments = list(
            StudioAssignment.objects.filter(offer__architect=studio.owner)
            .select_related("offer__application", "offer__application__owner", "offer__application__interior_style")
            .order_by("-created_at")
        )
        open_assignments = [a for a in assignments if a.status == StudioAssignment.Status.OPEN]
        my_assignments = sorted(
            (a for a in assignments if a.worker_id == profile.id and a.status == StudioAssignment.Status.ASSIGNED),
            # Overdue first, then the nearest deadline, then jobs without a deadline.
            key=lambda a: (not a.is_overdue, a.deadline is None, a.deadline or date.max),
        )
        my_done = [a for a in assignments if a.worker_id == profile.id and a.status == StudioAssignment.Status.DONE]
        colleagues = list(
            studio.employees.filter(approval_status=Approval.APPROVED).exclude(pk=profile.pk).select_related("user")
        )

    counts = {"tasks": len(my_assignments), "open": len(open_assignments), "done": len(my_done)}
    tabs = [(key, f"{label} ({counts[key]})" if counts.get(key) else label) for key, label in EMPLOYEE_TABS]
    tab = request.GET.get("tab")
    if tab not in {key for key, _ in EMPLOYEE_TABS}:
        tab = "tasks"

    return render(request, "architects/workspace.html", {
        "profile": profile,
        "title": studio.name if studio is not None else "Studiya",
        "tabs": tabs,
        "tab": tab,
        "tab_template": f"architects/tabs/_emp_{tab}.html",
        "portfolio_locked": False,
        "studio": studio,
        "colleagues": colleagues,
        "my_assignments": my_assignments,
        "open_assignments": open_assignments,
        "my_done": my_done,
        "emp_stats": {
            "active": len(my_assignments),
            "overdue": sum(1 for a in my_assignments if a.is_overdue),
            "done": len(my_done),
            "open": len(open_assignments),
        },
    })


@require_POST
@approved_architect_required(Kind.STUDIO_EMPLOYEE)
def assignment_claim(request, assignment_id):
    profile = request.architect_profile
    studio = profile.studio
    if studio is None:
        raise Http404
    assignment = get_object_or_404(StudioAssignment, pk=assignment_id, offer__architect=studio.owner)
    try:
        claim_assignment(assignment, profile)
    except (AssignmentAlreadyTakenError, WorkerNotInStudioError) as e:
        messages.warning(request, str(e))
    return redirect(dashboard_url(profile, "tasks"))


@require_POST
@approved_architect_required(Kind.STUDIO_EMPLOYEE)
def assignment_done(request, assignment_id):
    profile = request.architect_profile
    assignment = get_object_or_404(StudioAssignment, pk=assignment_id, worker=profile)
    mark_assignment_done(assignment)
    return redirect(dashboard_url(profile, "done"))


@require_POST
@approved_architect_required(Kind.STUDIO_OWNER)
def assignment_assign(request, assignment_id):
    profile = request.architect_profile
    assignment = get_object_or_404(StudioAssignment, pk=assignment_id, offer__architect=profile)
    worker_id = request.POST.get("worker")
    deadline_raw = (request.POST.get("deadline") or "").strip()
    deadline = None
    if deadline_raw:
        try:
            deadline = date.fromisoformat(deadline_raw)
        except ValueError:
            messages.warning(request, "Muddat sanasi noto'g'ri formatda.")
            return redirect(dashboard_url(profile, "orders"))

    if worker_id:
        worker = get_object_or_404(
            ArchitectProfile, pk=worker_id, kind=Kind.STUDIO_EMPLOYEE,
            studio=profile.studio_owned, approval_status=Approval.APPROVED,
        )
        try:
            assign_worker(assignment, worker, deadline=deadline)
        except WorkerNotInStudioError as e:
            messages.warning(request, str(e))
    elif deadline_raw:
        set_deadline(assignment, deadline)
    return redirect(dashboard_url(profile, "orders"))


@approved_architect_required(Kind.STUDIO_OWNER)
def employee_remove(request, profile_id):
    """Let a studio owner let an employee go. Asks first; a POST does it.

    The employee's login account stays, but their studio membership is deleted,
    so they lose the studio workspace and can register again (with this studio
    or another) whenever they like.
    """
    employee = get_object_or_404(
        ArchitectProfile,
        pk=profile_id,
        kind=Kind.STUDIO_EMPLOYEE,
        studio=request.architect_profile.studio_owned,
        approval_status=Approval.APPROVED,
    )
    if request.method == "POST":
        employee.delete()
        return redirect(dashboard_url(request.architect_profile, "employees"))
    return render(request, "architects/employee_remove_confirm.html", {"employee": employee})


@require_POST
@approved_architect_required(Kind.STUDIO_OWNER)
def employee_decision(request, profile_id):
    employee = get_object_or_404(
        ArchitectProfile,
        pk=profile_id,
        kind=Kind.STUDIO_EMPLOYEE,
        studio=request.architect_profile.studio_owned,
        approval_status=Approval.PENDING,
    )
    approved = request.POST.get("decision") == "accept"
    set_approval(employee, Approval.APPROVED if approved else Approval.REJECTED)
    return redirect(dashboard_url(request.architect_profile, "employees"))


@portfolio_builder_required
def portfolio(request):
    """The portfolio page for applicants whose application is still being reviewed
    (once approved, the same content lives in the "Mening xonam" tab)."""
    profile = request.architect_profile
    if profile.approval_status == Approval.APPROVED:
        return redirect(portfolio_url(profile))
    projects = list(profile.projects.select_related("style").prefetch_related("images"))
    return render(request, "architects/portfolio.html", {
        "profile": profile, "projects": projects, "progress": profile.portfolio_progress(projects),
    })


@portfolio_builder_required
def portfolio_edit(request):
    profile = request.architect_profile
    if request.method == "POST":
        form = ArchitectProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect(portfolio_url(profile))
    else:
        form = ArchitectProfileForm(instance=profile)
    return render(request, "architects/portfolio_form.html", {"form": form, "profile": profile})


@portfolio_builder_required
def project_create(request):
    """Create a whole portfolio project in one step: title, type, description,
    photos (the first is the cover) and one optional file."""
    profile = request.architect_profile
    if request.method == "POST":
        form = PortfolioProjectForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                project = form.save(commit=False)
                project.architect = profile
                project.order = (profile.projects.aggregate(Max("order"))["order__max"] or 0) + 1
                project.save()
                for index, uploaded in enumerate(form.cleaned_data["images"]):
                    PortfolioImage.objects.create(project=project, image=uploaded, order=index)
            return redirect(portfolio_url(profile))
    else:
        form = PortfolioProjectForm()
    return render(request, "architects/project_form.html", {
        "form": form, "progress": profile.portfolio_progress(), "portfolio_url": portfolio_url(profile),
    })


@portfolio_builder_required
def project_image_add(request, project_id):
    """Add more photos to a project later (they go after the ones already there,
    so the first photo stays the cover)."""
    profile = request.architect_profile
    project = get_object_or_404(profile.projects, id=project_id)
    if request.method == "POST":
        form = PortfolioImagesForm(request.POST, request.FILES)
        if form.is_valid():
            next_order = (project.images.aggregate(Max("order"))["order__max"] or 0) + 1
            for index, uploaded in enumerate(form.cleaned_data["images"]):
                PortfolioImage.objects.create(project=project, image=uploaded, order=next_order + index)
            return redirect("architects:my_project", project_id=project.pk)
    else:
        form = PortfolioImagesForm()
    return render(request, "architects/project_image_form.html", {"form": form, "project": project})


def _project_context(project, *, owner=False):
    profile = project.architect
    project_count = profile.projects.count() if owner else len(profile.visible_projects)
    pool = profile.projects.select_related("style").prefetch_related("images") if owner else profile.visible_projects
    return {
        "project": project,
        "profile": profile,
        "images": list(project.images.all()),
        "others": [p for p in pool if p.pk != project.pk],
        "project_count": project_count,
        "is_owner": owner,
    }


@portfolio_builder_required
def my_project(request, project_id):
    """An architect's own view of one of their projects: everything, including the
    file, plus a way to add more photos."""
    profile = request.architect_profile
    project = get_object_or_404(
        profile.projects.select_related("style", "architect__user").prefetch_related("images"), pk=project_id,
    )
    context = _project_context(project, owner=True)
    context["back_url"] = portfolio_url(profile)
    return render(request, "architects/project_detail.html", context)


@portfolio_builder_required
def project_edit(request, project_id):
    """Change a project's details or replace its file, and remove single photos."""
    profile = request.architect_profile
    project = get_object_or_404(profile.projects.select_related("style").prefetch_related("images"), pk=project_id)
    if request.method == "POST":
        form = PortfolioProjectEditForm(request.POST, request.FILES, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, "Loyiha yangilandi.")
            return redirect("architects:my_project", project_id=project.pk)
    else:
        form = PortfolioProjectEditForm(instance=project)
    return render(request, "architects/project_edit.html", {
        "form": form, "project": project, "images": list(project.images.all()),
    })


@portfolio_builder_required
@require_POST
def project_photo_delete(request, project_id, image_id):
    profile = request.architect_profile
    project = get_object_or_404(profile.projects, pk=project_id)
    image = get_object_or_404(project.images, pk=image_id)
    if project.images.count() <= 1:
        messages.error(request, "Loyihada kamida bitta rasm qolishi kerak. Avval yangi rasm qo'shing.")
    else:
        image.delete()
        messages.success(request, "Rasm o'chirildi.")
    return redirect("architects:project_edit", project_id=project.pk)


@portfolio_builder_required
def project_delete(request, project_id):
    """Ask for confirmation, then delete one of the architect's own projects."""
    profile = request.architect_profile
    project = get_object_or_404(profile.projects, pk=project_id)
    if request.method == "POST":
        project.delete()
        messages.success(request, "Loyiha o'chirildi.")
        return redirect(portfolio_url(profile))
    progress = profile.portfolio_progress()
    return render(request, "architects/project_delete_confirm.html", {
        "project": project,
        "drops_below": not profile.portfolio_exempt and progress["ready"] - (1 if profile.project_is_ready(project) else 0) < progress["need_projects"],
        "need_projects": progress["need_projects"],
    })


def project_detail(request, pk):
    """The public page of one project: its full description, all photos and file,
    and who made it (rating, skills and their other projects)."""
    project = get_object_or_404(
        PortfolioProject.objects.visible().select_related("style", "architect__user", "architect__studio_owned")
        .prefetch_related("images", "architect__skills", "architect__projects__images"),
        pk=pk,
    )
    context = _project_context(project)
    context["back_url"] = reverse("architects:project_gallery")
    return render(request, "architects/project_detail.html", context)


def public_list(request):
    profiles = (
        ArchitectProfile.objects.public()
        .select_related("user", "studio_owned")
        .prefetch_related("projects__images", "projects__style")
    )
    style_id = request.GET.get("style")
    if style_id:
        profiles = profiles.filter(styles__id=style_id).distinct()
    styles = Style.objects.all()
    return render(request, "architects/public_list.html", {"profiles": profiles, "styles": styles, "selected_style": style_id})


def public_detail(request, pk):
    profile = get_object_or_404(ArchitectProfile.objects.public().prefetch_related("projects__images", "styles", "skills"), pk=pk)
    style_id = request.GET.get("style")
    projects = profile.projects.all()
    if not profile.portfolio_exempt:
        # Projects only count (and show) once they have enough photos.
        projects = projects.annotate(photos=Count("images")).filter(photos__gte=profile.portfolio_requirements["images"])
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


def project_gallery(request):
    projects = (
        PortfolioProject.objects.visible()
        .select_related("architect__user", "architect__studio_owned", "style")
        .prefetch_related("images")
    )
    style_id = request.GET.get("style")
    if style_id:
        projects = projects.filter(style_id=style_id)
    styles = Style.objects.all()
    return render(request, "architects/project_gallery.html", {
        "projects": projects,
        "styles": styles,
        "selected_style": style_id,
    })
