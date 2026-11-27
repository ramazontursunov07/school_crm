from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import FamilyInvite

User = get_user_model()


class PersonSerializer(serializers.ModelSerializer):
    """Ikkinchi tomon haqida faqat eng zarur ma'lumot (email/telefon yo'q)."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name"]
        read_only_fields = fields


class InviteCreateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=FamilyInvite.Role.choices,
        help_text="Kodni yaratgan kishi kim: `parent` yoki `child`.",
    )


class InviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = FamilyInvite
        fields = ["id", "creator_role", "expires_at", "created_at"]
        read_only_fields = fields


class InviteCreatedSerializer(InviteSerializer):
    code = serializers.CharField(read_only=True)

    class Meta(InviteSerializer.Meta):
        fields = InviteSerializer.Meta.fields + ["code"]
        read_only_fields = fields


class AcceptSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)


class LinkSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    relation = serializers.ChoiceField(choices=["child", "parent"])
    user = PersonSerializer()
    created_at = serializers.DateTimeField()
    