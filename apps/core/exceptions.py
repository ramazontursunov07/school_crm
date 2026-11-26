from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, ValidationError):
        code = "validation_error"
        message = "Yuborilgan ma'lumotlarda xato bor."
        details = response.data
    else:
        detail = response.data.get("detail", "")
        code = getattr(detail, "code", "error")
        message = str(detail)
        details = None

    response.data = {
        "error": {"code": code, "message": message, "details": details}
    }
    return response
