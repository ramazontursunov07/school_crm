from django.core.management.base import BaseCommand

from apps.billing.models import Plan

# DIQQAT: bular boshlang'ich NAMUNA tariflar. Narx va cheklovlar haqiqiy
# biznes qarori emas: ishga tushirishdan oldin admin panelda o'zgartiring.
STARTER_PLANS = [
    {
        "code": "start",
        "name": "Start",
        "description": "Kichik o'quv markazi uchun.",
        "price_monthly": "99000",
        "price_yearly": "990000",
        "max_branches": 1,
        "max_staff": 5,
        "max_students": 100,
        "features": {"crm": True},
        "sort_order": 10,
    },
    {
        "code": "standard",
        "name": "Standart",
        "description": "O'sib borayotgan markaz va maktab uchun.",
        "price_monthly": "249000",
        "price_yearly": "2490000",
        "max_branches": 3,
        "max_staff": 20,
        "max_students": 500,
        "features": {"crm": True, "reports": True, "notifications": True},
        "sort_order": 20,
    },
    {
        "code": "pro",
        "name": "Pro",
        "description": "Ko'p filialli tashkilotlar uchun.",
        "price_monthly": "499000",
        "price_yearly": "4990000",
        "max_branches": 10,
        "max_staff": 100,
        "max_students": None,
        "features": {
            "crm": True,
            "reports": True,
            "marketplace": True,
            "mobile_app": True,
            "notifications": True,
        },
        "sort_order": 30,
    },
]


class Command(BaseCommand):
    help = (
        "Boshlang'ich namuna tariflarni yaratadi. Mavjud tarifga tegmaydi "
        "(qayta ishga tushirish xavfsiz)."
    )

    def handle(self, *args, **options):
        for data in STARTER_PLANS:
            _, created = Plan.objects.get_or_create(code=data["code"], defaults=data)
            state = "yaratildi" if created else "mavjud, o'zgartirilmadi"
            self.stdout.write(f"{data['code']}: {state}")
        self.stdout.write(
            self.style.WARNING("Narxlar namuna: admin panelda haqiqiy qiymatlarga o'zgartiring.")
        )
        