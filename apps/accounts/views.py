from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    NotFound,
    Throttled,
    ValidationError,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import get_client_ip, log_action

from .authentication import DeviceTokenAuthentication
from .delivery import send_code
from .models import DeviceToken, VerificationCode
from .serializers import (
    AuthResponseSerializer,
    CsrfSerializer,
    DeviceSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    TokenLoginSerializer,
    TokenResponseSerializer,
    UserSerializer,
    VerifyConfirmSerializer,
    VerifyRequestResponseSerializer,
    VerifyRequestSerializer,
)
from .services import (
    CODE_LIFETIME,
    RESEND_COOLDOWN,
    CodeRateLimited,
    authenticate_by_identifier,
    check_code,
    issue_code,
    mark_verified,
    resolve_reset_target,
)
from .tokens import (
    active_tokens,
    issue_token,
    revoke_all_tokens,
    revoke_token,
)
from .throttles import (
    CodeRequestIPThrottle,
    LoginIdentifierThrottle,
    LoginIPThrottle,
    PasswordResetIdentifierThrottle,
    PasswordResetIPThrottle,
    RegisterIPThrottle,
)

User = get_user_model()


def _auth_response(request, user, status_code=status.HTTP_200_OK):
    # login() CSRF tokenni yangilaydi, mijozga yangisi qaytariladi
    return Response(
        {"user": UserSerializer(user).data, "csrf_token": get_token(request)},
        status=status_code,
    )


@method_decorator(never_cache, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=CsrfSerializer)
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


# DRF kirmagan foydalanuvchida CSRF'ni tekshirmaydi, shu sababli
# register va login uchun csrf_protect alohida qo'yiladi
@method_decorator(
    [sensitive_post_parameters("password"), csrf_protect, never_cache],
    name="dispatch",
)
class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RegisterIPThrottle]

    @extend_schema(request=RegisterSerializer, responses={201: AuthResponseSerializer})
    def post(self, request):
        if request.user.is_authenticated:
            raise ValidationError({"detail": ["Avval tizimdan chiqing."]})
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        try:
            with transaction.atomic():
                user = User.objects.create_user(**data)
                log_action(
                    action="user.registered",
                    actor=user,
                    target=user,
                    request=request,
                )
        except IntegrityError:
            raise ValidationError(
                {"detail": ["Login, email yoki telefon allaqachon band."]}
            )
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return _auth_response(request, user, status.HTTP_201_CREATED)


@method_decorator(
    [sensitive_post_parameters("password"), csrf_protect, never_cache],
    name="dispatch",
)
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginIPThrottle, LoginIdentifierThrottle]

    @extend_schema(request=LoginSerializer, responses=AuthResponseSerializer)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate_by_identifier(request, **serializer.validated_data)
        if user is None:
            raise ValidationError({"detail": ["Login yoki parol noto'g'ri."]})
        login(request, user)
        log_action(action="user.logged_in", actor=user, target=user, request=request)
        return _auth_response(request, user)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        log_action(
            action="user.logged_out",
            actor=request.user,
            target=request.user,
            request=request,
        )
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(never_cache, name="dispatch")
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


INVALID_CODE = "Kod noto'g'ri yoki muddati o'tgan."

_CHANNELS = {
    "email": (VerificationCode.Purpose.VERIFY_EMAIL, "email", "is_email_verified"),
    "phone": (VerificationCode.Purpose.VERIFY_PHONE, "phone", "is_phone_verified"),
}


class CodeDeliveryFailed(APIException):
    status_code = 503
    default_detail = "Kodni yuborib bo'lmadi. Keyinroq urinib ko'ring."
    default_code = "code_delivery_failed"


@method_decorator(never_cache, name="dispatch")
class VerifyRequestView(APIView):
    """Akkauntdagi email yoki telefonga tasdiqlash kodini yuboradi."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [CodeRequestIPThrottle]

    @extend_schema(
        request=VerifyRequestSerializer, responses=VerifyRequestResponseSerializer
    )
    def post(self, request):
        serializer = VerifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channel = serializer.validated_data["channel"]
        purpose, field, verified_attr = _CHANNELS[channel]
        user = request.user
        target = getattr(user, field)
        if not target:
            raise ValidationError({"channel": ["Akkauntda bu kontakt yo'q."]})
        if getattr(user, verified_attr):
            raise ValidationError({"channel": ["Bu kontakt allaqachon tasdiqlangan."]})

        try:
            code = issue_code(user=user, purpose=purpose, target=target)
        except CodeRateLimited as error:
            raise Throttled(
                wait=error.wait,
                detail="Kod yaqinda yuborilgan. Biroz kutib, qayta urinib ko'ring.",
            )
        if not send_code(target=target, code=code):
            raise CodeDeliveryFailed()
        log_action(
            action="user.verification_requested",
            actor=user,
            target=user,
            metadata={"channel": channel},
            request=request,
        )
        return Response(
            {
                "expires_in": int(CODE_LIFETIME.total_seconds()),
                "resend_after": int(RESEND_COOLDOWN.total_seconds()),
            }
        )


@method_decorator(never_cache, name="dispatch")
class VerifyConfirmView(APIView):
    """Yuborilgan kodni tekshirib, email yoki telefonni tasdiqlaydi."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=VerifyConfirmSerializer, responses=UserSerializer)
    def post(self, request):
        serializer = VerifyConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        channel = serializer.validated_data["channel"]
        purpose, field, _ = _CHANNELS[channel]
        user = request.user
        target = getattr(user, field)
        ok = bool(target) and check_code(
            user=user,
            purpose=purpose,
            target=target,
            code=serializer.validated_data["code"],
        )
        if not ok:
            raise ValidationError({"code": [INVALID_CODE]})
        mark_verified(user, channel)
        log_action(
            action=f"user.{channel}_verified",
            actor=user,
            target=user,
            request=request,
        )
        return Response(UserSerializer(user).data)


@method_decorator(
    [sensitive_post_parameters("new_password"), csrf_protect, never_cache],
    name="dispatch",
)
class PasswordResetRequestView(APIView):
    """Parolni tiklash kodini TASDIQLANGAN email/telefonga yuboradi.

    Akkaunt bor-yo'qligidan qat'i nazar javob bir xil (204)."""

    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetIPThrottle, PasswordResetIdentifierThrottle]

    @extend_schema(request=PasswordResetRequestSerializer, responses={204: None})
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resolved = resolve_reset_target(serializer.validated_data["identifier"])
        if resolved is not None:
            user, target = resolved
            try:
                code = issue_code(
                    user=user,
                    purpose=VerificationCode.Purpose.PASSWORD_RESET,
                    target=target,
                )
            except CodeRateLimited:
                pass  # javob o'zgarmaydi: akkaunt borligi bildirilmaydi
            else:
                send_code(target=target, code=code)
                log_action(
                    action="user.password_reset_requested",
                    target=user,
                    metadata={"channel": "email" if "@" in target else "phone"},
                    request=request,
                )
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(
    [sensitive_post_parameters("new_password"), csrf_protect, never_cache],
    name="dispatch",
)
class PasswordResetConfirmView(APIView):
    """Kod bilan yangi parol o'rnatadi. Eski sessiyalar yopiladi."""

    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetIPThrottle, PasswordResetIdentifierThrottle]

    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None})
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        resolved = resolve_reset_target(data["identifier"])
        user = resolved[0] if resolved else None

        # Parol qoidalari akkaunt bor-yo'qligidan qat'i nazar bir xil tekshiriladi
        try:
            validate_password(
                data["new_password"], user or User(username=data["identifier"][:150])
            )
        except DjangoValidationError as error:
            raise ValidationError({"new_password": error.messages})

        ok = resolved is not None and check_code(
            user=user,
            purpose=VerificationCode.Purpose.PASSWORD_RESET,
            target=resolved[1],
            code=data["code"],
        )
        if not ok:
            raise ValidationError({"code": [INVALID_CODE]})

        # Parol xeshi o'zgargani uchun boshqa qurilmalardagi sessiyalar tugaydi
        user.set_password(data["new_password"])
        user.save(update_fields=["password"])
        # Mobil qurilmalardagi tokenlar ham yopiladi
        revoke_all_tokens(user)
        log_action(action="user.password_reset", actor=user, target=user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Mobil ilova: token orqali kirish ------------------------------------


@method_decorator(
    [sensitive_post_parameters("password"), never_cache], name="dispatch"
)
class TokenLoginView(APIView):
    """Mobil ilova uchun kirish. Sessiya va CSRF ishlatilmaydi: javobda
    `token` qaytadi, keyingi so'rovlarda `Authorization: Bearer <token>`.

    Token faqat shu javobda ko'rinadi (bazada xeshi saqlanadi)."""

    permission_classes = [AllowAny]
    # Kirish uchun autentifikatsiya kerak emas: eskirgan token yoki sessiya
    # cookie'si kirishga xalaqit bermasin va CSRF talab qilinmasin.
    authentication_classes = []
    throttle_classes = [LoginIPThrottle, LoginIdentifierThrottle]

    @extend_schema(request=TokenLoginSerializer, responses={201: TokenResponseSerializer})
    def post(self, request):
        serializer = TokenLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = authenticate_by_identifier(
            request, identifier=data["identifier"], password=data["password"]
        )
        if user is None:
            raise ValidationError({"detail": ["Login yoki parol noto'g'ri."]})
        token, raw_token = issue_token(
            user=user,
            device_name=data["device_name"],
            ip_address=get_client_ip(request),
        )
        log_action(
            action="user.token_issued",
            actor=user,
            target=user,
            metadata={"device_id": token.pk, "device_name": token.device_name},
            request=request,
        )
        return Response(
            {
                "token": raw_token,
                "token_type": "Bearer",
                "device_id": token.pk,
                "expires_at": token.expires_at,
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class CurrentTokenView(APIView):
    """Joriy qurilmadan chiqish (tokenni bekor qilish)."""

    permission_classes = [IsAuthenticated]
    authentication_classes = [DeviceTokenAuthentication]

    @extend_schema(request=None, responses={204: None})
    def delete(self, request):
        revoke_token(request.auth)
        log_action(
            action="user.token_revoked",
            actor=request.user,
            target=request.user,
            metadata={"device_id": request.auth.pk},
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(never_cache, name="dispatch")
class DeviceListView(APIView):
    """Akkauntga kirgan mobil qurilmalar ro'yxati."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=DeviceSerializer(many=True))
    def get(self, request):
        current_id = request.auth.pk if isinstance(request.auth, DeviceToken) else None
        devices = [
            {
                "id": token.pk,
                "device_name": token.device_name,
                "ip_address": token.ip_address,
                "created_at": token.created_at,
                "last_used_at": token.last_used_at,
                "expires_at": token.expires_at,
                "is_current": token.pk == current_id,
            }
            for token in active_tokens(request.user)
        ]
        return Response(DeviceSerializer(devices, many=True).data)


class DeviceDetailView(APIView):
    """Qurilmani tizimdan chiqarish. Faqat o'z qurilmangiz: boshqaniki 404."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, pk):
        token = active_tokens(request.user).filter(pk=pk).first()
        if token is None:
            raise NotFound("Qurilma topilmadi.")
        revoke_token(token)
        log_action(
            action="user.token_revoked",
            actor=request.user,
            target=request.user,
            metadata={"device_id": token.pk},
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceRevokeAllView(APIView):
    """Barcha mobil qurilmalardan chiqish."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        count = revoke_all_tokens(request.user)
        log_action(
            action="user.tokens_revoked_all",
            actor=request.user,
            target=request.user,
            metadata={"count": count},
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
    