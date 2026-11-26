from rest_framework import generics

from apps.organizations import roles
from apps.organizations.permissions import OrganizationScopedMixin
from apps.organizations.serializers import AuditLogSerializer

from .models import AuditLog


class AuditLogListView(OrganizationScopedMixin, generics.ListAPIView):
    """Tashkilot harakatlari tarixi. `?action=branch.created` bilan saralanadi."""

    serializer_class = AuditLogSerializer
    permission_map = {"GET": roles.AUDIT_VIEW}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AuditLog.objects.none()
        queryset = AuditLog.objects.filter(organization=self.organization).select_related(
            "actor"
        )
        action = self.request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)
        return queryset
    