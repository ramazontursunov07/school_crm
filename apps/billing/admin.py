from django import forms
from django.contrib import admin

from apps.audit.services import log_action

from .features import FEATURES
from .models import Plan, Subscription


class _PlanFormBase(forms.ModelForm):
    class Meta:
        model = Plan
        exclude = ("features",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = (self.instance.features if self.instance.pk else None) or {}
        for key in FEATURES:
            self.fields[f"feature_{key}"].initial = bool(current.get(key))

    def save(self, commit=True):
        self.instance.features = {
            key: bool(self.cleaned_data.get(f"feature_{key}")) for key in FEATURES
        }
        return super().save(commit=commit)


# Imkoniyatlar JSON o'rniga belgilash katakchalari bilan tahrirlanadi. Maydonlar
# sinf darajasida e'lon qilinishi shart (admin fieldsets shuni talab qiladi).
PlanAdminForm = type(
    "PlanAdminForm",
    (_PlanFormBase,),
    {
        f"feature_{key}": forms.BooleanField(label=label, required=False)
        for key, label in FEATURES.items()
    },
)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    form = PlanAdminForm
    list_display = (
        "name",
        "code",
        "audience",
        "price_monthly",
        "price_yearly",
        "currency",
        "is_active",
        "is_public",
        "sort_order",
    )
    list_filter = ("audience", "is_active", "is_public")
    search_fields = ("name", "code")
    ordering = ("sort_order", "id")
    fieldsets = (
        (None, {"fields": ("code", "name", "description", "audience")}),
        ("Narx", {"fields": ("currency", "price_monthly", "price_yearly")}),
        ("Sinov", {"fields": ("trial_days",)}),
        ("Cheklovlar (bo'sh = cheksiz)", {"fields": ("max_branches", "max_staff", "max_students")}),
        ("Imkoniyatlar", {"fields": tuple(f"feature_{key}" for key in FEATURES)}),
        ("Ko'rinish", {"fields": ("is_active", "is_public", "sort_order")}),
    )

    def get_readonly_fields(self, request, obj=None):
        # Kod barqaror identifikator: yaratilgandan keyin o'zgarmaydi.
        return ("code",) if obj else ()

    def has_delete_permission(self, request, obj=None):
        # Tariflar o'chirilmaydi, faqat "sotuvda" belgisi olinadi.
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        log_action(
            action="billing.plan_updated" if change else "billing.plan_created",
            actor=request.user,
            target=obj,
            metadata={"code": obj.code, "changed": sorted(form.changed_data)}
            if change
            else {"code": obj.code},
            request=request,
        )


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Faqat ko'rish. Sinovni uzaytirish va bekor qilish 6-qadamda (tarixga yozilgan holda)."""

    list_display = ("organization", "plan", "state", "trial_started_at", "trial_ends_at")
    list_filter = ("status", "plan")
    search_fields = ("organization__name",)
    raw_id_fields = ("organization", "trial_started_by")

    @admin.display(description="Holati")
    def state(self, obj):
        return Subscription.Status(obj.effective_status()).label

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
