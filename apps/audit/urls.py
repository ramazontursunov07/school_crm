from django.urls import path

from .views import AuditLogListView

urlpatterns = [
    path(
        "organizations/<int:org_id>/audit-logs/",
        AuditLogListView.as_view(),
        name="audit-log-list",
    ),
]
