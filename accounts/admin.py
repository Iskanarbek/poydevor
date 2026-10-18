from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from accounts.models import User
from accounts.services import freeze_account, unfreeze_account


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["phone"]
    list_display = ["phone", "first_name", "last_name", "role", "is_staff", "account_status"]
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Shaxsiy ma'lumot", {"fields": ("first_name", "last_name", "role")}),
        ("Ruxsatlar", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Muzlatish", {"fields": ("frozen_at", "frozen_reason")}),
    )
    readonly_fields = ["frozen_at"]
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("phone", "first_name", "last_name", "role", "password1", "password2"),
        }),
    )
    search_fields = ["phone", "first_name", "last_name"]

    @admin.display(description="Holati")
    def account_status(self, obj):
        url = reverse(
            f"admin:accounts_user_{'unfreeze' if not obj.is_active else 'freeze'}", args=[obj.pk],
        )
        if obj.is_active:
            return format_html(
                '<span style="color:#1b8049;font-weight:600">● Faol</span> '
                '&nbsp;<a href="{}" style="color:#be3434">Muzlatish</a>', url,
            )
        return format_html(
            '<span style="color:#be3434;font-weight:600">● Muzlatilgan</span>'
            '{}<br><a href="{}" style="color:#1b8049">Qaytarish</a>',
            format_html(' — {}', obj.frozen_reason) if obj.frozen_reason else "",
            url,
        )

    def get_urls(self):
        return [
            path("<int:pk>/freeze/", self.admin_site.admin_view(self.freeze_view), name="accounts_user_freeze"),
            path("<int:pk>/unfreeze/", self.admin_site.admin_view(self.unfreeze_view), name="accounts_user_unfreeze"),
            *super().get_urls(),
        ]

    def freeze_view(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if request.method == "POST":
            freeze_account(user, request.POST.get("reason", "").strip())
            messages.success(request, f"{user} muzlatildi.")
            return redirect("admin:accounts_user_changelist")
        return render(request, "admin/accounts/freeze_confirm.html", {"account": user, "opts": User._meta})

    def unfreeze_view(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        if request.method == "POST":
            unfreeze_account(user)
            messages.success(request, f"{user} qayta faollashtirildi.")
            return redirect("admin:accounts_user_changelist")
        return render(request, "admin/accounts/unfreeze_confirm.html", {"account": user, "opts": User._meta})
