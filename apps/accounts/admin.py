from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "phone", "is_staff", "is_active")
    search_fields = ("username", "email", "phone", "first_name", "last_name")
    readonly_fields = UserAdmin.readonly_fields + (
        "email_verified_at",
        "phone_verified_at",
    )
    fieldsets = UserAdmin.fieldsets + (
        ("Aloqa", {"fields": ("phone", "email_verified_at", "phone_verified_at")}),
    )
