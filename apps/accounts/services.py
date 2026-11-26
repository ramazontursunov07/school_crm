from django.contrib.auth import authenticate, get_user_model

from .validators import normalize_phone

User = get_user_model()


def authenticate_by_identifier(request, identifier, password):
    """Login, email yoki telefon bo'yicha tekshiradi."""
    identifier = identifier.strip()
    if "@" in identifier:
        users = User.objects.filter(email__iexact=identifier)
    elif identifier.startswith("+"):
        users = User.objects.filter(phone=normalize_phone(identifier) or identifier)
    else:
        users = None

    if users is None:
        username = identifier
    else:
        user = users.first()
        # Topilmasa ham authenticate chaqiriladi: javob vaqti orqali akkaunt
        # bor-yo'qligini bilish qiyinlashadi
        username = user.get_username() if user else ""

    return authenticate(request, username=username, password=password)
