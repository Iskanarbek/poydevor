from django.db import transaction

from accounts.models import User
from architects.models import ArchitectProfile, Studio
from wallet.models import Wallet
from wallet.services import grant_signup_bonus


def split_full_name(full_name: str) -> tuple[str, str]:
    first, _, last = full_name.strip().partition(" ")
    return first, last.strip()


def _account_for(phone: str, full_name: str, email: str, user: User | None) -> User:
    """The login account behind a registration.

    A brand-new person gets a passwordless account (they sign in with their
    phone number). A signed-in architect who never finished registering keeps
    their existing account and just gets a profile attached.
    """
    first_name, last_name = split_full_name(full_name)
    if user is None:
        user = User(phone=phone, role=User.Role.ARCHITECT)
        user.set_unusable_password()
    user.first_name, user.last_name, user.email = first_name, last_name, email
    user.save()
    return user


# Studios and freelancers are approved right away: there is no review to wait for. What
# stands between them and the orders is the portfolio they must build (see
# settings.PORTFOLIO_REQUIREMENTS). Studio employees still need their studio's approval.


@transaction.atomic
def register_studio(data: dict, user: User | None = None) -> ArchitectProfile:
    account = _account_for(data["phone"], data["responsible_person"], data["email"], user)
    profile = ArchitectProfile.objects.create(
        user=account,
        kind=ArchitectProfile.Kind.STUDIO_OWNER,
        approval_status=ArchitectProfile.ApprovalStatus.PENDING,   # switched to approved just below
        portfolio_exempt=False,
        birth_year=data["responsible_birth_date"].year,
        claimed_projects_count=data["projects_count"],
    )
    Studio.objects.create(
        owner=profile,
        name=data["studio_name"],
        founded_on=data["founded_on"],
        founders=data["founders"],
        responsible_person=data["responsible_person"],
        responsible_birth_date=data["responsible_birth_date"],
        email=data["email"],
        phone=data["phone"],
        staff_count=data["staff_count"],
        projects_count=data["projects_count"],
    )
    set_approval(profile, ArchitectProfile.ApprovalStatus.APPROVED)
    return profile


@transaction.atomic
def register_employee(data: dict, user: User | None = None) -> ArchitectProfile:
    account = _account_for(data["phone"], data["full_name"], data["email"], user)
    return ArchitectProfile.objects.create(
        user=account,
        kind=ArchitectProfile.Kind.STUDIO_EMPLOYEE,
        approval_status=ArchitectProfile.ApprovalStatus.PENDING,
        portfolio_exempt=False,
        studio=data["studio"],
        birth_year=data["birth_year"],
    )


@transaction.atomic
def register_freelancer(data: dict, user: User | None = None) -> ArchitectProfile:
    account = _account_for(data["phone"], data["full_name"], data["email"], user)
    profile = ArchitectProfile.objects.create(
        user=account,
        kind=ArchitectProfile.Kind.FREELANCER,
        approval_status=ArchitectProfile.ApprovalStatus.PENDING,
        portfolio_exempt=False,
        birth_year=data["birth_year"],
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
