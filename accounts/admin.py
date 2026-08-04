from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["phone"]
    list_display = ["phone", "first_name", "last_name", "role", "is_staff"]
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Shaxsiy ma'lumot", {"fields": ("first_name", "last_name", "role")}),
        ("Ruxsatlar", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("phone", "first_name", "last_name", "role", "password1", "password2"),
        }),
    )
    search_fields = ["phone", "first_name", "last_name"]
