from django.urls import path

from .views import (
    AcceptInvitationView,
    BranchViewSet,
    InvitationViewSet,
    MemberViewSet,
    OrganizationDetailView,
    OrganizationListCreateView,
)

branch_list = BranchViewSet.as_view({"get": "list", "post": "create"})
branch_detail = BranchViewSet.as_view({"get": "retrieve", "patch": "partial_update"})
member_list = MemberViewSet.as_view({"get": "list"})
member_detail = MemberViewSet.as_view({"get": "retrieve", "patch": "partial_update"})
invitation_list = InvitationViewSet.as_view({"get": "list", "post": "create"})
invitation_detail = InvitationViewSet.as_view({"delete": "destroy"})

urlpatterns = [
    path("organizations/", OrganizationListCreateView.as_view(), name="organization-list"),
    path(
        "organizations/<int:org_id>/",
        OrganizationDetailView.as_view(),
        name="organization-detail",
    ),
    path("organizations/<int:org_id>/branches/", branch_list, name="branch-list"),
    path(
        "organizations/<int:org_id>/branches/<int:pk>/",
        branch_detail,
        name="branch-detail",
    ),
    path("organizations/<int:org_id>/members/", member_list, name="member-list"),
    path(
        "organizations/<int:org_id>/members/<int:pk>/",
        member_detail,
        name="member-detail",
    ),
    path(
        "organizations/<int:org_id>/invitations/",
        invitation_list,
        name="invitation-list",
    ),
    path(
        "organizations/<int:org_id>/invitations/<int:pk>/",
        invitation_detail,
        name="invitation-detail",
    ),
    path(
        "invitations/accept/",
        AcceptInvitationView.as_view(),
        name="invitation-accept",
    ),
]
