from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny

from apps.organizations.models import Organization

from .models import Plan
from .serializers import PlanSerializer
from .throttles import CatalogThrottle


def sellable_plans():
    """Narxlar sahifasida ko'rinadigan tariflar."""
    return Plan.objects.filter(is_active=True, is_public=True)


class PublicCatalogMixin:
    # Narxlar sahifasi kirishsiz ochiq. Autentifikatsiya o'chirilgan, shunda
    # eskirgan token yoki cookie ro'yxatni buzmaydi.
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [CatalogThrottle]
    serializer_class = PlanSerializer


class PlanListView(PublicCatalogMixin, generics.ListAPIView):
    """Sotuvdagi ochiq tariflar. `?organization_type=learning_center` bilan
    shu turga mos (va barcha turlar uchun) tariflar chiqadi."""

    pagination_class = None  # tariflar kam: oddiy ro'yxat

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Plan.objects.none()
        queryset = sellable_plans()
        org_type = self.request.query_params.get("organization_type")
        if org_type:
            if org_type not in Organization.Type.values:
                raise ValidationError(
                    {"organization_type": ["Noma'lum tashkilot turi."]}
                )
            queryset = queryset.filter(audience__in=[Plan.Audience.ANY, org_type])
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "organization_type",
                str,
                enum=Organization.Type.values,
                description="Tashkilot turi bo'yicha saralash",
            )
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PlanDetailView(PublicCatalogMixin, generics.RetrieveAPIView):
    lookup_field = "code"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Plan.objects.none()
        return sellable_plans()
    