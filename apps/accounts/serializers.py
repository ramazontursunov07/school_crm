from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .validators import normalize_phone

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    email_verified = serializers.BooleanField(
        source="is_email_verified", read_only=True
    )
    phone_verified = serializers.BooleanField(
        source="is_phone_verified", read_only=True
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "email_verified",
            "phone_verified",
        ]
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(
        max_length=150, validators=[UnicodeUsernameValidator()]
    )
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name = serializers.CharField(max_length=150, required=False, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(
        max_length=30, required=False, allow_blank=True, default=""
    )

    def validate_username(self, value):
        # Login email yoki telefonga o'xshab, boshqa odam kontakti bilan
        # adashtirilmasligi kerak
        if "@" in value or value.startswith("+"):
            raise serializers.ValidationError(
                "Loginda '@' bo'lmasin va u '+' bilan boshlanmasin."
            )
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Bu login band.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Bu email band.")
        return value

    def validate_phone(self, value):
        if not value.strip():
            return ""
        phone = normalize_phone(value)
        if phone is None:
            raise serializers.ValidationError(
                "Telefonni xalqaro formatda kiriting: +998901234567."
            )
        if User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError("Bu telefon raqami band.")
        return phone

    def validate(self, attrs):
        if not attrs["email"] and not attrs["phone"]:
            raise serializers.ValidationError(
                {"detail": ["Email yoki telefon raqamini kiriting."]}
            )
        user = User(
            **{key: value for key, value in attrs.items() if key != "password"}
        )
        try:
            validate_password(attrs["password"], user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages})
        return attrs


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )


class AuthResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    csrf_token = serializers.CharField()


class CsrfSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


class VerifyRequestSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=["email", "phone"])


class VerifyConfirmSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=["email", "phone"])
    code = serializers.CharField(max_length=10)


class VerifyRequestResponseSerializer(serializers.Serializer):
    expires_in = serializers.IntegerField()
    resend_after = serializers.IntegerField()


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    code = serializers.CharField(max_length=10)
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )
