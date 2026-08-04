from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from architects.models import ArchitectProfile
from wallet.models import Wallet


class BuyCoinsViewTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=user, bio="x")
        self.wallet = Wallet.objects.create(architect=self.profile)
        self.client.force_login(user)

    def test_buy_coins_credits_balance(self):
        response = self.client.post(reverse("wallet:buy"), {"package": "20"})
        self.assertEqual(response.status_code, 302)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 20)
