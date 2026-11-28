from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations import roles
from apps.organizations.models import Organization
from apps.organizations.permissions import OrganizationScopedMixin

from . import services
from .models import Plan
from .serializers import (
    PlanSerializer,
    StartTrialSerializer,
    SubscriptionSerializer,
    SubscriptionStateSerializer,
)
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


class SubscriptionView(OrganizationScopedMixin, APIView):
    """Tashkilotning joriy obunasi (sinov holati) va sinov boshlash mumkinligi."""

    permission_map = {"GET": roles.BILLING_VIEW}
    allow_inactive_org = True

    @extend_schema(responses=SubscriptionStateSerializer)
    def get(self, request, org_id):
        state = {
            "subscription": services.current_subscription(self.organization),
            "trial_available": services.trial_available(self.organization, request.user),
        }
        return Response(SubscriptionStateSerializer(state).data)


class StartTrialView(OrganizationScopedMixin, APIView):
    """Tanlangan tarif bo'yicha sinov boshlash. Muddatni mijoz belgilay olmaydi."""

    permission_map = {"POST": roles.BILLING_MANAGE}

    @extend_schema(request=StartTrialSerializer, responses={201: SubscriptionSerializer})
    def post(self, request, org_id):
        serializer = StartTrialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscription = services.start_trial(
            organization=self.organization,
            plan_code=serializer.validated_data["plan"],
            user=request.user,
            request=request,
        )
        return Response(
            SubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED
        )
