from django.conf import settings
from django.db import models


class Style(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Skill(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ArchitectProfileQuerySet(models.QuerySet):
    def takers(self):
        """Approved studios and freelancers: the architects who can take part in
        orders. Studio employees work under their studio and never do."""
        return self.filter(approval_status=ArchitectProfile.ApprovalStatus.APPROVED).exclude(
            kind=ArchitectProfile.Kind.STUDIO_EMPLOYEE,
        )

    def public(self):
        """Architects clients can see and hire: approved, with a finished portfolio
        (or excused from having one), and admin-verified (or excused from that too)."""
        return self.takers().filter(
            models.Q(portfolio_complete=True) | models.Q(portfolio_exempt=True),
        ).filter(
            models.Q(portfolio_verification=ArchitectProfile.VerificationStatus.VERIFIED)
            | models.Q(portfolio_exempt=True),
        )


class ArchitectProfile(models.Model):
    class Kind(models.TextChoices):
        STUDIO_OWNER = "studio_owner", "Studiya egasi"
        STUDIO_EMPLOYEE = "studio_employee", "Studiya xodimi"
        FREELANCER = "freelancer", "Individual arxitektor"

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Ko'rib chiqilmoqda"
        APPROVED = "approved", "Tasdiqlangan"
        REJECTED = "rejected", "Rad etilgan"

    class VerificationStatus(models.TextChoices):
        NOT_READY = "not_ready", "Portfolio to'liq emas"
        PENDING = "pending", "Admin tekshiruvida"
        VERIFIED = "verified", "Tasdiqlangan"
        REJECTED = "rejected", "Rad etilgan"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="architect_profile")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.FREELANCER)
    # Defaults to approved so profiles created by hand (admin, seed data) and
    # every profile that existed before approvals were introduced keep working.
    # The registration forms always create profiles as PENDING explicitly.
    approval_status = models.CharField(
        max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.APPROVED,
    )
    studio = models.ForeignKey(
        "Studio", null=True, blank=True, on_delete=models.SET_NULL, related_name="employees",
    )
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
    # Self-reported at registration; ``completed_projects_count`` below is the
    # number completed through Poydevor itself.
    claimed_projects_count = models.PositiveIntegerField(default=0)
    # True once the architect has built the portfolio the platform requires (see
    # settings.PORTFOLIO_REQUIREMENTS). Kept up to date automatically whenever a
    # project or photo is added or removed (architects/signals.py).
    portfolio_complete = models.BooleanField(default=False)
    # Excuses an architect from the portfolio requirement. Defaults to True so that
    # accounts that existed before the requirement, and profiles created by hand
    # (admin, seed data), keep working; the registration flow creates profiles with
    # this switched off. The admin can change it per architect.
    portfolio_exempt = models.BooleanField(default=True)
    # A studio owner's or freelancer's finished portfolio still needs an admin to look it
    # over before they may apply to or accept orders (employees and exempt profiles skip
    # this — see ``verification_ok``). Flips to PENDING automatically once the portfolio
    # is complete (architects/signals.py via recompute_portfolio); an admin then verifies
    # or rejects it (architects/admin.py, architects/services.py::decide_verification).
    portfolio_verification = models.CharField(
        max_length=10, choices=VerificationStatus.choices, default=VerificationStatus.NOT_READY,
    )
    portfolio_verified_at = models.DateTimeField(null=True, blank=True)
    # Shown back to the architect when the admin rejects their portfolio.
    verification_note = models.CharField(max_length=255, blank=True)
    bio = models.TextField(blank=True)
    telegram_username = models.CharField(max_length=50, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True, max_length=500)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    completed_projects_count = models.PositiveIntegerField(default=0)
    styles = models.ManyToManyField(Style, related_name="architects", blank=True)
    skills = models.ManyToManyField(Skill, related_name="architects", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ArchitectProfileQuerySet.as_manager()

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name}"

    # --- portfolio -----------------------------------------------------

    @property
    def portfolio_requirements(self):
        """``{"projects": n, "images": m}`` for this kind of architect, or None
        (employees don't keep a portfolio)."""
        key = {self.Kind.STUDIO_OWNER: "studio", self.Kind.FREELANCER: "freelancer"}.get(self.kind)
        return settings.PORTFOLIO_REQUIREMENTS.get(key) if key else None

    @property
    def portfolio_ok(self):
        """Finished portfolio, or excused from it."""
        return self.portfolio_complete or self.portfolio_exempt

    @property
    def verification_ok(self):
        """The admin has looked over the finished portfolio (or the architect is
        excused from one entirely). Employees never need this — they work under
        their studio's own verification."""
        if self.portfolio_exempt or self.kind == self.Kind.STUDIO_EMPLOYEE:
            return True
        return self.portfolio_verification == self.VerificationStatus.VERIFIED

    @property
    def awaiting_verification(self):
        return (
            not self.portfolio_exempt
            and self.kind != self.Kind.STUDIO_EMPLOYEE
            and self.portfolio_verification == self.VerificationStatus.PENDING
        )

    def project_is_ready(self, project):
        """A project counts towards the portfolio once it has enough photos."""
        req = self.portfolio_requirements
        return bool(req) and len(project.images.all()) >= req["images"]

    def portfolio_progress(self, projects=None):
        """Where the architect stands, for the progress bars and notices."""
        req = self.portfolio_requirements or {"projects": 0, "images": 0}
        projects = list(projects if projects is not None else self.projects.all())
        for project in projects:
            # Handy for the templates: how many photos, and how many are still missing.
            project.photo_count = len(project.images.all())
            project.photos_missing = max(0, req["images"] - project.photo_count)
        ready = sum(1 for project in projects if self.project_is_ready(project))
        return {
            "need_projects": req["projects"],
            "need_images": req["images"],
            "ready": ready,
            "total": len(projects),
            "missing": max(0, req["projects"] - ready),
            "percent": min(100, round(ready / req["projects"] * 100)) if req["projects"] else 100,
            "complete": bool(req) and ready >= req["projects"],
        }

    def recompute_portfolio(self):
        """Refresh ``portfolio_complete`` from the projects and photos in the database.

        Also keeps ``portfolio_verification`` in step: finishing the portfolio for the
        first time (or editing it again after a rejection) sends it to the admin queue;
        falling back below the requirement (e.g. a photo was removed) pulls a
        still-unreviewed portfolio back out of that queue. A portfolio that is already
        VERIFIED stays verified through further edits — an admin can always move it back
        by hand if a resubmission needs a fresh look.
        """
        req = self.portfolio_requirements
        complete = False
        if req:
            ready = self.projects.annotate(photos=models.Count("images")).filter(photos__gte=req["images"]).count()
            complete = ready >= req["projects"]
        self.portfolio_complete = complete
        verification = self.portfolio_verification
        if complete and verification in (self.VerificationStatus.NOT_READY, self.VerificationStatus.REJECTED):
            verification = self.VerificationStatus.PENDING
        elif not complete and verification == self.VerificationStatus.PENDING:
            verification = self.VerificationStatus.NOT_READY
        self.portfolio_verification = verification
        # update() rather than save(): this also runs while a profile is being deleted.
        type(self).objects.filter(pk=self.pk).update(
            portfolio_complete=complete, portfolio_verification=verification,
        )
        return complete

    @property
    def visible_projects(self):
        """The projects other people can see: all of them for an excused
        architect, otherwise only those with enough photos."""
        return [
            project for project in self.projects.all()
            if self.portfolio_exempt or self.project_is_ready(project)
        ]

    @property
    def all_images(self):
        """Every photo of the visible projects, in order."""
        return [image for project in self.visible_projects for image in project.images.all()]

    @property
    def carousel_images(self):
        """The photos shown on this architect's card: the cover (first photo) of every
        visible project, so a card with several projects changes by itself."""
        return [project.cover for project in self.visible_projects if project.cover is not None]

    @property
    def project_styles(self):
        """The distinct types of the visible projects (for the chips on the card)."""
        names = []
        for project in self.visible_projects:
            if project.style and project.style.name not in names:
                names.append(project.style.name)
        return names

    @property
    def display_name(self):
        """What the site calls this architect: the studio's name for a studio,
        otherwise the person's name."""
        if self.kind == self.Kind.STUDIO_OWNER:
            studio = getattr(self, "studio_owned", None)
            if studio is not None:
                return studio.name
        return str(self)

    @property
    def is_approved(self):
        return self.approval_status == self.ApprovalStatus.APPROVED

    @property
    def can_take_offers(self):
        """Approved studios and freelancers with a finished, admin-verified portfolio
        can apply to orders and accept offers; employees never do."""
        return (
            self.is_approved
            and self.kind != self.Kind.STUDIO_EMPLOYEE
            and self.portfolio_ok
            and self.verification_ok
        )


class Studio(models.Model):
    owner = models.OneToOneField(ArchitectProfile, on_delete=models.CASCADE, related_name="studio_owned")
    name = models.CharField(max_length=150)
    founded_on = models.DateField()
    founders = models.CharField(max_length=255)
    responsible_person = models.CharField(max_length=150)
    responsible_birth_date = models.DateField()
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    staff_count = models.PositiveIntegerField()
    projects_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class RegistrationFile(models.Model):
    """A portfolio file (image/PDF/video) uploaded with a registration form."""

    profile = models.ForeignKey(ArchitectProfile, on_delete=models.CASCADE, related_name="registration_files")
    # 500 chars: with Vercel Blob storage the stored name is the full CDN URL.
    file = models.FileField(upload_to="registration/", max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class PortfolioProjectQuerySet(models.QuerySet):
    def visible(self):
        """Projects other people may see: those of architects with a public
        profile and, unless the architect is excused, only projects that have
        enough photos."""
        enough = models.Q()
        for kind, key in (
            (ArchitectProfile.Kind.STUDIO_OWNER, "studio"),
            (ArchitectProfile.Kind.FREELANCER, "freelancer"),
        ):
            enough |= models.Q(architect__kind=kind, photos__gte=settings.PORTFOLIO_REQUIREMENTS[key]["images"])
        return (
            self.filter(architect__in=ArchitectProfile.objects.public())
            .annotate(photos=models.Count("images"))
            .filter(models.Q(architect__portfolio_exempt=True) | enough)
        )


class PortfolioProject(models.Model):
    architect = models.ForeignKey(ArchitectProfile, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    style = models.ForeignKey(Style, on_delete=models.SET_NULL, null=True, related_name="projects")
    order = models.PositiveIntegerField(default=0)
    # One optional file with the project (a PDF presentation, drawings, ...).
    attachment = models.FileField(upload_to="portfolio_files/", blank=True, max_length=500)

    objects = PortfolioProjectQuerySet.as_manager()

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title

    @property
    def cover(self):
        """The project's first photo: it is what cards show first."""
        return next(iter(self.images.all()), None)

    @property
    def attachment_ext(self):
        import os
        return os.path.splitext(self.attachment.name)[1].lstrip(".")[:4] if self.attachment else ""

    @property
    def attachment_name(self):
        import os
        return os.path.basename(self.attachment.name) if self.attachment else ""


class PortfolioImage(models.Model):
    project = models.ForeignKey(PortfolioProject, on_delete=models.CASCADE, related_name="images")
    # max_length raised from Django's 100-char default: when Vercel Blob
    # storage is active (see poydevor/storage_backends.py), the "name"
    # stored here is the entire Blob CDN URL, which is well over 100 chars.
    image = models.ImageField(upload_to="portfolio/", max_length=500)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
