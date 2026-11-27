from rest_framework.throttling import SimpleRateThrottle


class _UserThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class FamilyAcceptThrottle(_UserThrottle):
    """Kodni tanlab ko'rishdan himoya: foydalanuvchi bo'yicha."""

    scope = "family_accept"


class FamilyInviteThrottle(_UserThrottle):
    scope = "family_invite"
    