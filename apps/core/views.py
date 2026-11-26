from django.http import JsonResponse
from django.views import defaults
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer("Health", {"status": serializers.CharField()})
    )
    def get(self, request):
        return Response({"status": "ok"})


def _api_error(status, code, message):
    return JsonResponse(
        {"error": {"code": code, "message": message, "details": None}},
        status=status,
    )


def _is_api(request):
    return request.path.startswith("/api/")


# Django'ning 400/403/404/500 sahifalari. /api/ manzillarida DRF xatolari bilan
# bir xil JSON qaytadi, qolgan manzillarda (masalan admin) standart sahifa.
def bad_request(request, exception=None):
    if _is_api(request):
        return _api_error(400, "bad_request", "So'rov noto'g'ri.")
    return defaults.bad_request(request, exception)


def permission_denied(request, exception=None):
    if _is_api(request):
        return _api_error(403, "permission_denied", "Bu amalni bajarishga ruxsat yo'q.")
    return defaults.permission_denied(request, exception)


def not_found(request, exception=None):
    if _is_api(request):
        return _api_error(404, "not_found", "Manzil topilmadi.")
    return defaults.page_not_found(request, exception)


def server_error(request):
    if _is_api(request):
        return _api_error(500, "server_error", "Serverda kutilmagan xato yuz berdi.")
    return defaults.server_error(request)
