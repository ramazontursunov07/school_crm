from .models import AuditLog


def get_client_ip(request):
    # Faqat REMOTE_ADDR. X-Forwarded-For soxtalashtirilishi mumkin; proksi
    # ortida ishlaganda to'g'ri sozlash 9-bosqichda (serverga joylash) qilinadi.
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None


def log_action(
    *, action, organization=None, actor=None, target=None, metadata=None, request=None
):
    """Harakatni tarixga yozadi. `metadata` JSON'ga o'tadigan bo'lishi kerak."""
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    target_type = target_id = ""
    if target is not None:
        target_type = f"{target._meta.app_label}.{target._meta.model_name}"
        target_id = str(target.pk)
    return AuditLog.objects.create(
        organization=organization,
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata or {},
        ip_address=get_client_ip(request),
    )
