from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "phone", "is_staff", "is_active")
    search_fields = ("username", "email", "phone", "first_name", "last_name")
    fieldsets = UserAdmin.fieldsets + (
        ("Aloqa", {"fields": ("phone",)}),
    )
