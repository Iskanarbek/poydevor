from datetime import date

from django.db import transaction

from accounts.models import User
from architects.models import ArchitectProfile, Studio
from wallet.models import Wallet
from architects.navigation import dashboard_url
from notifications.services import notify
from wallet.services import grant_signup_bonus


def split_full_name(full_name: str) -> tuple[str, str]:
    first, _, last = full_name.strip().partition(" ")
    return first, last.strip()


def _account_for(phone: str, full_name: str, user: User | None, password: str) -> User:
    """The login account behind a registration.

    A brand-new person gets an account with the password they chose (architects sign in
    with phone + password). A signed-in architect who never finished registering keeps
    their existing account, gets the password set and a profile attached.
    """
    first_name, last_name = split_full_name(full_name)
    if user is None:
        user = User(phone=phone, role=User.Role.ARCHITECT)
    user.set_password(password)
    user.first_name, user.last_name = first_name, last_name
    user.save()
    return user


# Studios and freelancers are approved right away: there is no review to wait for. What
# stands between them and the orders is the portfolio they must build (see
# settings.PORTFOLIO_REQUIREMENTS). Studio employees still need their studio's approval.


@transaction.atomic
def register_studio(data: dict, user: User | None = None) -> ArchitectProfile:
    account = _account_for(data["phone"], data["responsible_person"], user, data["password"])
    profile = ArchitectProfile.objects.create(
        user=account,
        kind=ArchitectProfile.Kind.STUDIO_OWNER,
        approval_status=ArchitectProfile.ApprovalStatus.PENDING,   # switched to approved just below
        portfolio_exempt=False,
        telegram_username=data["telegram_username"],
        claimed_projects_count=data["projects_count"],
    )
    Studio.objects.create(
        owner=profile,
        name=data["studio_name"],
        founded_on=date(data["founded_year"], 1, 1),
        responsible_person=data["responsible_person"],
        phone=data["phone"],
        projects_count=data["projects_count"],
    )
    set_approval(profile, ArchitectProfile.ApprovalStatus.APPROVED)
    return profile


@transaction.atomic
def register_employee(data: dict, user: User | None = None) -> ArchitectProfile:
    account = _account_for(data["phone"], data["full_name"], user, data["password"])
    employee = ArchitectProfile.objects.create(
        user=account,
        kind=ArchitectProfile.Kind.STUDIO_EMPLOYEE,
        approval_status=ArchitectProfile.ApprovalStatus.PENDING,
        portfolio_exempt=False,
        studio=data["studio"],
        birth_year=data["birth_year"],
        telegram_username=data["telegram_username"],
    )
    notify(
        data["studio"].owner, f"{account.first_name} {account.last_name} studiyangizga qo'shilmoqchi. Tasdiqlang yoki rad eting.",
        dashboard_url(data["studio"].owner, "employees"),
    )
    return employee


@transaction.atomic
def register_freelancer(data: dict, user: User | None = None) -> ArchitectProfile:
    account = _account_for(data["phone"], data["full_name"], user, data["password"])
    profile = ArchitectProfile.objects.create(
        user=account,
        kind=ArchitectProfile.Kind.FREELANCER,
        approval_status=ArchitectProfile.ApprovalStatus.PENDING,
        portfolio_exempt=False,
        birth_year=data["birth_year"],
        telegram_username=data["telegram_username"],
        claimed_projects_count=data["projects_count"],
    )
    set_approval(profile, ArchitectProfile.ApprovalStatus.APPROVED)
    return profile


@transaction.atomic
def decide_verification(profile: ArchitectProfile, status: str, note: str = "") -> None:
    """Admin verifies or rejects a finished portfolio. Only meaningful for studio
    owners and freelancers whose portfolio is awaiting review; called from
    ArchitectProfileAdmin's actions."""
    from django.utils import timezone

    profile.portfolio_verification = status
    profile.verification_note = note
    update_fields = ["portfolio_verification", "verification_note"]
    if status == ArchitectProfile.VerificationStatus.VERIFIED:
        profile.portfolio_verified_at = timezone.now()
        update_fields.append("portfolio_verified_at")
    profile.save(update_fields=update_fields)
    if status == ArchitectProfile.VerificationStatus.VERIFIED:
        notify(profile, "Portfolioingiz tasdiqlandi! Endi e'lonlarda qatnasha olasiz.", dashboard_url(profile, "market"))
    elif status == ArchitectProfile.VerificationStatus.REJECTED:
        reason = f" Sabab: {note}" if note else ""
        notify(profile, f"Portfolioingiz tasdiqlanmadi.{reason}", dashboard_url(profile, "room"))


@transaction.atomic
def set_approval(profile: ArchitectProfile, status: str) -> None:
    """Approve or reject an architect.

    Studios and freelancers get their wallet, with the sign-up bonus (coins for
    two projects), the moment they are approved. The bonus is granted once, so
    re-approving an account is harmless. Employees never hold coins.
    """
    profile.approval_status = status
    profile.save(update_fields=["approval_status"])
    if (
        status == ArchitectProfile.ApprovalStatus.APPROVED
        and profile.kind != ArchitectProfile.Kind.STUDIO_EMPLOYEE
    ):
        wallet, _ = Wallet.objects.get_or_create(architect=profile)
        grant_signup_bonus(wallet)
    if profile.kind == ArchitectProfile.Kind.STUDIO_EMPLOYEE and profile.studio_id:
        studio_name = profile.studio.name
        if status == ArchitectProfile.ApprovalStatus.APPROVED:
            notify(profile, f"{studio_name} studiyasi sizni qabul qildi. Buyurtmalarni ko'rishingiz mumkin.", dashboard_url(profile, "open"))
        elif status == ArchitectProfile.ApprovalStatus.REJECTED:
            notify(profile, f"{studio_name} studiyasi arizangizni rad etdi.", "")
