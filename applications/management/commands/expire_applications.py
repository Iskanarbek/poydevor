from django.core.management.base import BaseCommand

from applications.services import expire_stale_applications


class Command(BaseCommand):
    help = (
        "Deletes open orders whose owner didn't confirm within ORDER_LIFETIME_DAYS and "
        "refunds the architects who paid to apply. Safe to run as often as you like."
    )

    def handle(self, *args, **options):
        removed = expire_stale_applications()
        self.stdout.write(self.style.SUCCESS(f"{removed} ta muddati o'tgan e'lon o'chirildi."))
