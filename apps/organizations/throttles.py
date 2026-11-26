from rest_framework.throttling import SimpleRateThrottle


class InvitationAcceptThrottle(SimpleRateThrottle):
    """Taklif tokenini tanlab ko'rishdan himoya: foydalanuvchi bo'yicha."""

    scope = "invitation_accept"

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
