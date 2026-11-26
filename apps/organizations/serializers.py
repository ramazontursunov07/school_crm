from django.contrib.auth import get_user_model
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.audit.models import AuditLog

from .models import Branch, Invitation, Membership, Organization
from .roles import Role, can_assign

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    my_role = serializers.CharField(read_only=True)
    country = serializers.RegexField(
        r"^[A-Za-z]{2}$",
        default="UZ",
        error_messages={"invalid": "Davlat kodi 2 harfdan iborat bo'lishi kerak."},
    )

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "type",
            "country",
            "is_active",
            "my_role",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "is_active", "created_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Nom bo'sh bo'lishi mumkin emas.")
        return value

    def validate_country(self, value):
        return value.upper()


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name", "address", "phone", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Nom bo'sh bo'lishi mumkin emas.")
        duplicates = Branch.objects.filter(
            organization=self.context["organization"], name__iexact=value
        )
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                "Bu nomli filial allaqachon mavjud."
            )
        return value


@extend_schema_field(OpenApiTypes.INT)
class OrganizationBranchField(serializers.PrimaryKeyRelatedField):
    """Faqat joriy tashkilotning faol filiallarini qabul qiladi. Boshqa
    tashkilot filiali 'topilmadi' xatosini beradi."""

    def get_queryset(self):
        return Branch.objects.filter(
            organization=self.context["organization"], is_active=True
        )


class UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone"]
        read_only_fields = fields


class MemberSerializer(serializers.ModelSerializer):
    user = UserBriefSerializer(read_only=True)
    branch = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "role", "branch", "is_active", "joined_at"]
        read_only_fields = fields


class MemberUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.choices, required=False)
    branch = OrganizationBranchField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)


class InvitationSerializer(serializers.ModelSerializer):
    status = serializers.CharField(source="effective_status", read_only=True)
    branch = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Invitation
        fields = [
            "id",
            "email",
            "phone",
            "role",
            "branch",
            "status",
            "invited_by",
            "expires_at",
            "created_at",
        ]
        read_only_fields = fields


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=20
    )
    role = serializers.ChoiceField(choices=Role.choices)
    branch = OrganizationBranchField(required=False, allow_null=True)

    def validate_role(self, value):
        if not can_assign(self.context["membership"].role, value):
            raise serializers.ValidationError("Bu rolni berishga ruxsat yo'q.")
        return value

    def validate(self, attrs):
        # User modeli bilan bir xil normalizatsiya
        email = (attrs.get("email") or "").strip().lower() or None
        phone = (attrs.get("phone") or "").strip() or None
        if not email and not phone:
            raise serializers.ValidationError(
                {"detail": "Email yoki telefon raqamini kiriting."}
            )
        attrs["email"] = email
        attrs["phone"] = phone
        attrs.setdefault("branch", None)
        return attrs


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class AuditLogSerializer(serializers.ModelSerializer):
    actor = UserBriefSerializer(read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor",
            "action",
            "target_type",
            "target_id",
            "metadata",
            "ip_address",
            "created_at",
        ]
        read_only_fields = fields
        