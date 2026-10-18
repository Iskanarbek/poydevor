from django.test import TestCase

from accounts.models import User
from architects.models import ArchitectProfile
from wallet.models import CoinTransaction, Wallet
from wallet.services import InsufficientCoinsError, spend_coins, topup_coins


class WalletServiceTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            phone="+998901234567", password="x",
            first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=user, bio="x")
        self.wallet = Wallet.objects.create(architect=self.profile)

    def test_topup_increases_balance_and_logs_transaction(self):
        topup_coins(self.wallet, 20)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 20)
        self.assertEqual(
            CoinTransaction.objects.filter(wallet=self.wallet, reason=CoinTransaction.Reason.TOPUP).count(), 1,
        )

    def test_spend_decreases_balance(self):
        topup_coins(self.wallet, 20)
        spend_coins(self.wallet, 20)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)

    def test_spend_more_than_balance_raises(self):
        with self.assertRaises(InsufficientCoinsError):
            spend_coins(self.wallet, 20)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)


class SignupBonusAndPricingTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            phone="+998901234567", first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=user, bio="x")
        self.wallet = Wallet.objects.create(architect=self.profile)

    def test_bonus_covers_exactly_two_projects(self):
        from django.conf import settings
        from wallet.services import grant_signup_bonus
        self.assertTrue(grant_signup_bonus(self.wallet))
        self.assertEqual(self.wallet.balance, 2 * settings.OFFER_COST_COINS)
        self.assertFalse(grant_signup_bonus(self.wallet))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 20)

    def test_pricing(self):
        from wallet.services import coin_price_uzs
        self.assertEqual(coin_price_uzs(10), 100_000)
        self.assertEqual(coin_price_uzs(1), 10_000)

    def test_credit_and_refund_order_are_idempotent(self):
        from wallet.models import PaymentOrder
        from wallet.services import credit_order, refund_order
        order = PaymentOrder.objects.create(wallet=self.wallet, provider="payme", coins=10, amount_uzs=100_000)
        self.assertTrue(credit_order(order))
        self.assertFalse(credit_order(order))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 10)
        self.assertTrue(refund_order(order))
        self.assertFalse(refund_order(order))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)
