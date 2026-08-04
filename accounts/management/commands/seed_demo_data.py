from django.core.management.base import BaseCommand

from accounts.models import User
from architects.models import ArchitectProfile, Skill, Style
from wallet.models import Wallet
from wallet.services import topup_coins


class Command(BaseCommand):
    help = "Creates demo data: a few styles/skills and one architect account with 1000 coins."

    def handle(self, *args, **options):
        for name in ["Zamonaviy", "Klassik", "Minimalizm", "Loft"]:
            Style.objects.get_or_create(name=name)
        for name in ["3D vizualizatsiya", "Landshaft dizayni", "Interyer dizayni", "Qurilish nazorati"]:
            Skill.objects.get_or_create(name=name)

        demo_phone = "+998900000000"
        if not User.objects.filter(phone=demo_phone).exists():
            user = User.objects.create_user(
                phone=demo_phone, password="demo12345",
                first_name="Demo", last_name="Arxitektor", role=User.Role.ARCHITECT,
            )
            profile = ArchitectProfile.objects.create(user=user, bio="Demo hisob, sinov uchun.")
            wallet = Wallet.objects.create(architect=profile)
            topup_coins(wallet, 1000)
            self.stdout.write(self.style.SUCCESS(f"Demo arxitektor yaratildi: {demo_phone} / demo12345 (1000 tanga)"))
        else:
            self.stdout.write("Demo hisob allaqachon mavjud.")
