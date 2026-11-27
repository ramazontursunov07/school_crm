from django.urls import path

from .views import (
    AcceptView,
    InviteDetailView,
    InviteListCreateView,
    LinkDetailView,
    LinkListView,
)

urlpatterns = [
    path("family/invites/", InviteListCreateView.as_view(), name="family-invite-list"),
    path(
        "family/invites/<int:pk>/",
        InviteDetailView.as_view(),
        name="family-invite-detail",
    ),
    path("family/links/accept/", AcceptView.as_view(), name="family-accept"),
    path("family/links/", LinkListView.as_view(), name="family-link-list"),
    path("family/links/<int:pk>/", LinkDetailView.as_view(), name="family-link-detail"),
]
