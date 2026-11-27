from django.contrib import admin

from .models import FamilyInvite, ParentChildLink


@admin.register(ParentChildLink)
class ParentChildLinkAdmin(admin.ModelAdmin):
    list_display = ("parent", "child", "created_at", "revoked_at")
    list_filter = ("revoked_at",)
    raw_id_fields = ("parent", "child", "revoked_by")
    readonly_fields = ("created_at",)


@admin.register(FamilyInvite)
class FamilyInviteAdmin(admin.ModelAdmin):
    list_display = ("creator", "creator_role", "expires_at", "used_at", "cancelled_at")
    raw_id_fields = ("creator", "used_by")
    readonly_fields = ("code_hash", "created_at")
    