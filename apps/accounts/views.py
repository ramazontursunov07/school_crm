from django.contrib.auth import get_user_model, login, logout
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import log_action

from .serializers import (
    AuthResponseSerializer,
    CsrfSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .services import authenticate_by_identifier
from .throttles import LoginIdentifierThrottle, LoginIPThrottle, RegisterIPThrottle

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
    