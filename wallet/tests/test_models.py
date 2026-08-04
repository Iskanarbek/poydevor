from django.test import TestCase

from accounts.models import User
from architects.models import ArchitectProfile
from wallet.models import Wallet


class WalletModelTests(TestCase):
    def test_wallet_created_with_zero_balance(self):
        user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        profile = ArchitectProfile.objects.create(user=user, bio="x")
        wallet = Wallet.objects.create(architect=profile)
        self.assertEqual(wallet.balance, 0)
