from django.db import IntegrityError
from django.db.models import OuterRef, Subquery
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import log_action

from . import roles, services
from .models import Branch, Invitation, Membership, Organization
from .permissions import OrganizationScopedMixin
from .serializers import (
    AcceptInvitationSerializer,
    BranchSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    MemberSerializer,
    MemberUpdateSerializer,
    OrganizationSerializer,
)
from .throttles import InvitationAcceptThrottle


def _changes(instance, validated_data):
    return {
        field: {"old": getattr(instance, field), "new": value}
        for field, value in validated_data.items()
        if getattr(instance, field) != value
    }


class OrganizationListCreateView(generics.ListCreateAPIView):
    """Foydalanuvchi a'zo bo'lgan tashkilotlar; yangi tashkilot yaratish."""

    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        my_role = Membership.objects.filter(
            organization=OuterRef("pk"), user=self.request.user, is_active=True
        ).values("role")[:1]
        return Organization.objects.annotate(my_role=Subquery(my_role)).filter(
            my_role__isnull=False
        )

    def perform_create(self, serializer):
        data = serializer.validated_data
        organization = services.create_organization(
            user=self.request.user,
            name=data["name"],
            type=data["type"],
            country=data["country"],
            request=self.request,
        )
        organization.my_role = roles.Role.OWNER
        serializer.instance = organization


class OrganizationDetailView(OrganizationScopedMixin, generics.RetrieveUpdateAPIView):
    serializer_class = OrganizationSerializer
    http_method_names = ["get", "patch", "head", "options"]
    permission_map = {"GET": roles.ORG_VIEW, "PATCH": roles.ORG_MANAGE}
    allow_inactive_org = True

    def get_object(self):
        organization = self.organization
        organization.my_role = self.membership.role
        return organization

    def perform_update(self, serializer):
        changes = _changes(serializer.instance, serializer.validated_data)
        serializer.save()
        if changes:
            log_action(
                action="organization.updated",
                organization=self.organization,
                actor=self.request.user,
                target=self.organization,
                metadata={"changes": changes},
                request=self.request,
            )


class BranchViewSet(
    OrganizationScopedMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Filiallar. O'chirish yo'q: filial `is_active=false` qilinadi, chunki
    keyingi bosqichlarda unga guruh, to'lov va hokazo bog'lanadi."""

    serializer_class = BranchSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_map = {
        "GET": roles.BRANCH_VIEW,
        "POST": roles.BRANCH_MANAGE,
        "PATCH": roles.BRANCH_MANAGE,
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Branch.objects.none()
        return Branch.objects.filter(organization=self.organization)

    def perform_create(self, serializer):
        try:
            branch = serializer.save(organization=self.organization)
        except IntegrityError:
            raise ValidationError({"name": ["Bu nomli filial allaqachon mavjud."]})
        log_action(
            action="branch.created",
            organization=self.organization,
            actor=self.request.user,
            target=branch,
            metadata={"name": branch.name},
            request=self.request,
        )

    def perform_update(self, serializer):
        changes = _changes(serializer.instance, serializer.validated_data)
        try:
            branch = serializer.save()
        except IntegrityError:
            raise ValidationError({"name": ["Bu nomli filial allaqachon mavjud."]})
        if changes:
            log_action(
                action="branch.updated",
                organization=self.organization,
                actor=self.request.user,
                target=branch,
                metadata={"changes": changes},
                request=self.request,
            )


class MemberViewSet(
    OrganizationScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = MemberSerializer
    http_method_names = ["get", "patch", "head", "options"]
    permission_map = {
        "GET": roles.MEMBERS_VIEW,
        "PATCH": roles.MEMBERS_MANAGE,
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Membership.objects.none()
        return Membership.objects.filter(organization=self.organization).select_related(
            "user", "branch"
        )

    @extend_schema(request=MemberUpdateSerializer, responses=MemberSerializer)
    def partial_update(self, request, *args, **kwargs):
        target = self.get_object()
        serializer = MemberUpdateSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        target = services.update_membership(
            target=target,
            actor_membership=self.membership,
            changes=serializer.validated_data,
            request=request,
        )
        return Response(MemberSerializer(target).data)


class InvitationViewSet(
    OrganizationScopedMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Xodimlarni taklif qilish. DELETE taklifni bekor qiladi."""

    serializer_class = InvitationSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]
    permission_map = {
        "GET": roles.MEMBERS_INVITE,
        "POST": roles.MEMBERS_INVITE,
        "DELETE": roles.MEMBERS_INVITE,
    }

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Invitation.objects.none()
        return Invitation.objects.filter(organization=self.organization)

    @extend_schema(request=InvitationCreateSerializer, responses=InvitationSerializer)
    def create(self, request, *args, **kwargs):
        serializer = InvitationCreateSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        invitation, raw_token = services.create_invitation(
            organization=self.organization,
            inviter_membership=self.membership,
            email=data["email"],
            phone=data["phone"],
            role=data["role"],
            branch=data["branch"],
            request=request,
        )
        # Xom token faqat shu javobda ko'rinadi, keyin tiklab bo'lmaydi.
        # Email/SMS orqali yuborish 8-bosqichda qo'shiladi.
        body = {**InvitationSerializer(invitation).data, "token": raw_token}
        return Response(body, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        services.revoke_invitation(
            invitation=instance, actor_membership=self.membership, request=self.request
        )


class AcceptInvitationView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [InvitationAcceptThrottle]

    @extend_schema(
        request=AcceptInvitationSerializer, responses=OrganizationSerializer
    )
    def post(self, request):
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.accept_invitation(
            user=request.user,
            raw_token=serializer.validated_data["token"],
            request=request,
        )
        organization = membership.organization
        organization.my_role = membership.role
        return Response(OrganizationSerializer(organization).data)
    