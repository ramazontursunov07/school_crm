from django.conf import settings
from django.http import JsonResponse


class RequestSizeLimitMiddleware:
    """Juda katta so'rovlarni o'qishdan oldin rad etadi (413).

    JSON uchun `API_MAX_JSON_BODY`, fayl yuklash (multipart) uchun
    `API_MAX_UPLOAD_BODY`. Faqat `/api/` manzillari. Tekshiruv
    `Content-Length` sarlavhasiga tayanadi; chunked so'rovlarni web server
    (nginx `client_max_body_size`) cheklashi kerak: 9-bosqich."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/"):
            try:
                length = int(request.META.get("CONTENT_LENGTH") or 0)
            except ValueError:
                length = 0
            multipart = request.content_type == "multipart/form-data"
            limit = (
                settings.API_MAX_UPLOAD_BODY if multipart else settings.API_MAX_JSON_BODY
            )
            if length > limit:
                return JsonResponse(
                    {
                        "error": {
                            "code": "request_too_large",
                            "message": "So'rov hajmi juda katta.",
                            "details": None,
                        }
                    },
                    status=413,
                )
        return self.get_response(request)
