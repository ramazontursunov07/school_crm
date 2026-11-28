from django.core.management.base import BaseCommand

from apps.billing.services import expire_due_trials


class Command(BaseCommand):
    help = "Muddati o'tgan sinovlarni 'expired' holatiga o'tkazadi (qayta ishga tushirish xavfsiz)."

    def handle(self, *args, **options):
        closed = expire_due_trials()
        self.stdout.write(f"Yopilgan sinovlar: {closed}")
