from django.urls import reverse

from architects.models import ArchitectProfile


def dashboard_url(profile: ArchitectProfile, tab: str | None = None) -> str:
    """Where an approved architect's home screen lives, by architect type."""
    route = {
        ArchitectProfile.Kind.STUDIO_OWNER: "architects:studio_dashboard",
        ArchitectProfile.Kind.FREELANCER: "architects:freelancer_dashboard",
        ArchitectProfile.Kind.STUDIO_EMPLOYEE: "architects:employee_workspace",
    }[profile.kind]
    url = reverse(route)
    return f"{url}?tab={tab}" if tab else url


def portfolio_url(profile: ArchitectProfile) -> str:
    """Where an architect builds their portfolio: the "Mening xonam" tab once
    approved, or a standalone page while the application is still being reviewed."""
    if profile.approval_status == ArchitectProfile.ApprovalStatus.APPROVED:
        return dashboard_url(profile, "room")
    return reverse("architects:portfolio")
