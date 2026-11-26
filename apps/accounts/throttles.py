import hashlib

from rest_framework.throttling import SimpleRateThrottle

from .validators import normalize_phone


class _IPThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class LoginIPThrottle(_IPThrottle):
    scope = "login_ip"


class RegisterIPThrottle(_IPThrottle):
    scope = "register_ip"


class LoginIdentifierThrottle(SimpleRateThrottle):
    """Bitta akkaunt parolini turli IP'lardan tanlashni cheklaydi."""

    scope = "login_identifier"

    def get_cache_key(self, request, view):
        data = request.data if hasattr(request.data, "get") else {}
        identifier = str(data.get("identifier", "")).strip().lower()
        if not identifier:
            return None
        if identifier.startswith("+"):
            identifier = normalize_phone(identifier) or identifier
        ident = hashlib.sha256(identifier.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}


class CodeRequestIPThrottle(_IPThrottle):
    scope = "code_request_ip"


class PasswordResetIPThrottle(_IPThrottle):
    scope = "password_reset_ip"


class PasswordResetIdentifierThrottle(LoginIdentifierThrottle):
    """Bitta akkaunt uchun parolni tiklash urinishlarini cheklaydi."""

    scope = "password_reset_identifier"
