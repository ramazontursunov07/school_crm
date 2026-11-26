from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated

from . import roles
from .models import Membership


class OrganizationPermission(BasePermission):
    """Tashkilot ichidagi har bir so'rovni tekshiradi.

    1. Foydalanuvchi shu tashkilotning faol a'zosimi? Yo'q bo'lsa 404
       (tashkilot mavjudligi ham sirli qoladi).
    2. Tashkilot faolmi?
    3. Rolida shu so'rov uchun ruxsat bormi? `view.permission_map` da
       ko'rsatilmagan usul rad etiladi.

    Muvaffaqiyatli bo'lsa `request.organization` va `request.membership`
    o'rnatiladi.
    """

    def has_permission(self, request, view):
        membership = (
            Membership.objects.select_related("organization", "branch")
            .filter(
                user=request.user,
                organization_id=view.kwargs.get("org_id"),
                is_active=True,
            )
            .first()
        )
        if membership is None:
            raise NotFound("Tashkilot topilmadi.")

        organization = membership.organization
        if not organization.is_active and not (
            getattr(view, "allow_inactive_org", False)
            and request.method in SAFE_METHODS
        ):
            raise PermissionDenied("Tashkilot faol emas.")

        request.organization = organization
        request.membership = membership

        if request.method == "OPTIONS" or request.method not in view.allowed_methods:
            # Ruxsat etilmagan usul uchun 405 ni DRF o'zi qaytaradi.
            return True
        method = "GET" if request.method == "HEAD" else request.method
        permission = getattr(view, "permission_map", {}).get(method)
        if permission is None or not roles.has_permission(membership.role, permission):
            raise PermissionDenied("Bu amalni bajarishga ruxsat yo'q.")
        return True


class OrganizationScopedMixin:
    """Tashkilotga tegishli view'lar uchun. `org_id` URL'dan olinadi.

    Ma'lumotni har doim `self.organization` bo'yicha filtrlang."""

    permission_classes = [IsAuthenticated, OrganizationPermission]
    permission_map = {}
    allow_inactive_org = False

    @property
    def organization(self):
        return self.request.organization

    @property
    def membership(self):
        return self.request.membership

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if hasattr(self.request, "organization"):
            context["organization"] = self.request.organization
            context["membership"] = self.request.membership
        return context
    