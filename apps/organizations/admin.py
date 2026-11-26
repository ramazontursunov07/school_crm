from django.contrib import admin

from .models import Branch, Invitation, Membership, Organization


class BranchInline(admin.TabularInline):
    model = Branch
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "country", "is_active", "created_at")
    list_filter = ("type", "is_active", "country")
    search_fields = ("name", "slug")
    inlines = [BranchInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "branch", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("user__username", "user__email", "organization__name")
    raw_id_fields = ("user", "organization", "branch")


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "phone", "organization", "role", "status", "expires_at")
    list_filter = ("status", "role")
    search_fields = ("email", "phone", "organization__name")
    readonly_fields = ("token_hash", "invited_by", "accepted_by", "accepted_at")
    raw_id_fields = ("organization", "branch")
