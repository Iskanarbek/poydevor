from django.core.management.base import BaseCommand

from offers.services import notify_overdue_assignments


class Command(BaseCommand):
    help = "Send the 'worker missed the deadline' news (also happens automatically when pages open)."

    def handle(self, *args, **options):
        self.stdout.write(f"{notify_overdue_assignments()} ta yangilik yuborildi.")
