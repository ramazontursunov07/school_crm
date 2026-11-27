from django.db import IntegrityError
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import log_action

from . import services
from .serializers import (
    AcceptSerializer,
    InviteCreatedSerializer,
    InviteCreateSerializer,
    InviteSerializer,
    LinkSerializer,
)
from .throttles import FamilyAcceptThrottle, FamilyInviteThrottle


def _link_data(link, user):
    """`user` nuqtai nazaridan: ikkinchi tomon kim."""
    if link.parent_id == user.pk:
        return {
            "id": link.pk,
            "relation": "child",
            "user": link.child,
            "created_at": link.created_at,
        }
    return {
        "id": link.pk,
        "relation": "parent",
        "user": link.parent,
        "created_at": link.created_at,
    }


class InviteListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.request.method == "POST":
            return [FamilyInviteThrottle()]
        return []

    @extend_schema(responses=InviteSerializer(many=True))
    def get(self, request):
        invites = services.active_invites(request.user)
        return Response(InviteSerializer(invites, many=True).data)

    @extend_schema(
        request=InviteCreateSerializer, responses={201: InviteCreatedSerializer}
    )
    def post(self, request):
        serializer = InviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite, code = services.create_invite(
            user=request.user, role=serializer.validated_data["role"]
        )
        log_action(
            action="family.invite_created",
            actor=request.user,
            target=invite,
            metadata={"role": invite.creator_role},
            request=request,
        )
        data = InviteSerializer(invite).data
        data["code"] = code
        return Response(data, status=status.HTTP_201_CREATED)


class InviteDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, pk):
        invite = services.active_invites(request.user).filter(pk=pk).first()
        if invite is None:
            raise NotFound("Kod topilmadi.")
        invite.cancelled_at = timezone.now()
        invite.save(update_fields=["cancelled_at"])
        log_action(
            action="family.invite_cancelled",
            actor=request.user,
            target=invite,
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AcceptView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [FamilyAcceptThrottle]

    @extend_schema(request=AcceptSerializer, responses={201: LinkSerializer})
    def post(self, request):
        serializer = AcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            link = services.accept_invite(
                user=request.user, code=serializer.validated_data["code"]
            )
        except IntegrityError:
            raise ValidationError({"detail": ["Bu akkauntlar allaqachon bog'langan."]})
        log_action(
            action="family.linked",
            actor=request.user,
            target=link,
            metadata={"parent_id": link.parent_id, "child_id": link.child_id},
            request=request,
        )
        return Response(
            LinkSerializer(_link_data(link, request.user)).data,
            status=status.HTTP_201_CREATED,
        )


class LinkListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LinkSerializer(many=True))
    def get(self, request):
        links = [
            _link_data(link, request.user)
            for link in services.active_links(request.user)
        ]
        return Response(LinkSerializer(links, many=True).data)


class LinkDetailView(APIView):
    """Bog'lanishni bekor qilish: ota-ona ham, farzand ham qila oladi."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, pk):
        link = services.active_links(request.user).filter(pk=pk).first()
        if link is None:
            raise NotFound("Bog'lanish topilmadi.")
        services.revoke_link(link=link, by=request.user)
        log_action(
            action="family.unlinked",
            actor=request.user,
            target=link,
            metadata={"parent_id": link.parent_id, "child_id": link.child_id},
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
