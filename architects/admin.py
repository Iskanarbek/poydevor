from django.contrib import admin, messages

from architects.models import (
    ArchitectProfile,
    PortfolioImage,
    PortfolioProject,
    RegistrationFile,
    Skill,
    Studio,
    Style,
)
from architects.services import decide_verification, set_approval

Approval = ArchitectProfile.ApprovalStatus
Verification = ArchitectProfile.VerificationStatus


class PortfolioImageInline(admin.TabularInline):
    model = PortfolioImage
    extra = 1


class PortfolioProjectInline(admin.TabularInline):
    model = PortfolioProject
    extra = 0


class RegistrationFileInline(admin.TabularInline):
    model = RegistrationFile
    extra = 0
    readonly_fields = ["uploaded_at"]


@admin.register(ArchitectProfile)
class ArchitectProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user", "kind", "approval_status", "portfolio_verification", "studio",
        "rating", "completed_projects_count", "created_at",
    ]
    list_filter = ["approval_status", "portfolio_verification", "kind"]
    search_fields = ["user__first_name", "user__last_name", "user__phone"]
    inlines = [RegistrationFileInline, PortfolioProjectInline]
    actions = ["approve", "reject", "verify_portfolio", "reject_portfolio"]
    readonly_fields = ["portfolio_verified_at"]

    def save_model(self, request, obj, form, change):
        # Going through set_approval makes an approval from the edit form do
        # the same as the "approve" action: create the wallet + sign-up bonus.
        new_status = obj.approval_status
        if change and "approval_status" in form.changed_data:
            obj.approval_status = form.initial.get("approval_status", new_status)
        super().save_model(request, obj, form, change)
        if change and "approval_status" in form.changed_data:
            set_approval(obj, new_status)

    @admin.action(description="Tanlanganlarni tasdiqlash")
    def approve(self, request, queryset):
        for profile in queryset:
            set_approval(profile, Approval.APPROVED)
        self.message_user(request, f"{queryset.count()} ta arxitektor tasdiqlandi.", messages.SUCCESS)

    @admin.action(description="Tanlanganlarni rad etish")
    def reject(self, request, queryset):
        for profile in queryset:
            set_approval(profile, Approval.REJECTED)
        self.message_user(request, f"{queryset.count()} ta arxitektor rad etildi.", messages.WARNING)

    @admin.action(description="Portfolioni tasdiqlash (loyihalarda qatnashishga ruxsat)")
    def verify_portfolio(self, request, queryset):
        candidates = queryset.filter(portfolio_verification=Verification.PENDING)
        count = candidates.count()
        for profile in candidates:
            decide_verification(profile, Verification.VERIFIED)
        self.message_user(request, f"{count} ta portfolio tasdiqlandi.", messages.SUCCESS)

    @admin.action(description="Portfolioni rad etish")
    def reject_portfolio(self, request, queryset):
        candidates = queryset.filter(portfolio_verification=Verification.PENDING)
        count = candidates.count()
        for profile in candidates:
            decide_verification(profile, Verification.REJECTED)
        self.message_user(request, f"{count} ta portfolio rad etildi.", messages.WARNING)


@admin.register(Studio)
class StudioAdmin(admin.ModelAdmin):
    list_display = ["name", "responsible_person", "phone", "staff_count", "projects_count", "owner"]
    search_fields = ["name", "responsible_person", "phone"]


@admin.register(PortfolioProject)
class PortfolioProjectAdmin(admin.ModelAdmin):
    inlines = [PortfolioImageInline]


admin.site.register(Style)
admin.site.register(Skill)
