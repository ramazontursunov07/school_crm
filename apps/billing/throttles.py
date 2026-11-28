from rest_framework.throttling import SimpleRateThrottle


class CatalogThrottle(SimpleRateThrottle):
    """Ochiq tariflar ro'yxati: IP bo'yicha."""

    scope = "public_catalog"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
    