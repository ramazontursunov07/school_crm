from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .tokens import find_token, touch_token


class DeviceTokenAuthentication(BaseAuthentication):
    """`Authorization: Bearer <token>` — mobil ilova uchun.

    Token orqali kirishda CSRF kerak emas (brauzer uni o'zi yubormaydi).
    Sessiya cookie'si bor so'rovlarda avval SessionAuthentication ishlaydi."""

    keyword = b"bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != self.keyword:
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("Authorization sarlavhasi noto'g'ri.")
        try:
            raw_token = parts[1].decode("ascii")
        except UnicodeDecodeError:
            raise AuthenticationFailed("Token yaroqsiz.")
        token = find_token(raw_token)
        if token is None:
            raise AuthenticationFailed("Token yaroqsiz yoki muddati o'tgan.")
        touch_token(token)
        return token.user, token

    def authenticate_header(self, request):
        return "Bearer"


class DeviceTokenScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.DeviceTokenAuthentication"
    name = "deviceToken"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer"}
    