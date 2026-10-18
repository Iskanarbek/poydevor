import base64

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from architects.models import ArchitectProfile
from wallet.models import PaymentOrder, Wallet

PAYME = {"MERCHANT_ID": "merchant-1", "KEY": "payme-secret", "TEST_MODE": True}
CLICK = {"SERVICE_ID": "111", "MERCHANT_ID": "222", "SECRET_KEY": "click-secret"}
NOT_CONFIGURED = {"MERCHANT_ID": "", "KEY": ""}
NOT_CONFIGURED_CLICK = {"SERVICE_ID": "", "MERCHANT_ID": "", "SECRET_KEY": ""}


class WalletTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user(
            phone="+998901234567", first_name="Nodir", last_name="Yusupov", role=User.Role.ARCHITECT,
        )
        self.profile = ArchitectProfile.objects.create(user=user, bio="x")
        self.wallet = Wallet.objects.create(architect=self.profile)
        self.client.force_login(user)


class StoreTabTests(WalletTestCase):
    def test_wallet_url_redirects_into_store_tab(self):
        response = self.client.get(reverse("wallet:dashboard"))
        self.assertRedirects(response, "/freelancer/dashboard/?tab=store", fetch_redirect_response=False)

    @override_settings(PAYME=NOT_CONFIGURED, CLICK=NOT_CONFIGURED_CLICK)
    def test_store_renders_without_any_payment_credentials(self):
        response = self.client.get("/freelancer/dashboard/?tab=store")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "hali ulanmagan")
        self.assertNotContains(response, "Tez orada")
        self.assertNotContains(response, "orqali to")

    @override_settings(PAYME=PAYME, CLICK=CLICK)
    def test_store_offers_both_providers_with_prices(self):
        response = self.client.get("/freelancer/dashboard/?tab=store")
        self.assertContains(response, "Payme orqali to")
        self.assertContains(response, "Click orqali to")
        packages = {p["coins"]: p for p in response.context["packages"]}
        self.assertEqual(packages[10]["price_uzs"], 100_000)
        self.assertEqual(packages[10]["projects"], 1)
        self.assertEqual(packages[100]["price_uzs"], 1_000_000)

    @override_settings(PAYME=PAYME, CLICK=NOT_CONFIGURED_CLICK)
    def test_only_configured_provider_is_offered(self):
        response = self.client.get("/freelancer/dashboard/?tab=store")
        self.assertContains(response, "Payme orqali to")
        self.assertNotContains(response, "Click orqali to")


class BuyCoinsViewTests(WalletTestCase):
    @override_settings(PAYME=PAYME, CLICK=CLICK)
    def test_payme_purchase_creates_order_and_redirects_to_checkout(self):
        response = self.client.post(reverse("wallet:buy"), {"coins": "10", "provider": "payme"})
        order = PaymentOrder.objects.get()
        self.assertEqual((order.coins, order.amount_uzs, order.provider), (10, 100_000, "payme"))
        self.assertEqual(order.amount_tiyin, 10_000_000)
        self.assertEqual(order.status, PaymentOrder.Status.CREATED)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("https://test.paycom.uz/"))
        decoded = base64.b64decode(response.url.rsplit("/", 1)[1]).decode()
        self.assertIn("m=merchant-1", decoded)
        self.assertIn(f"ac.order_id={order.pk}", decoded)
        self.assertIn("a=10000000", decoded)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 0)  # nothing is credited until the provider confirms

    @override_settings(PAYME={**PAYME, "TEST_MODE": False}, CLICK=CLICK)
    def test_live_payme_uses_production_checkout(self):
        response = self.client.post(reverse("wallet:buy"), {"coins": "10", "provider": "payme"})
        self.assertTrue(response.url.startswith("https://checkout.paycom.uz/"))

    @override_settings(PAYME=PAYME, CLICK=CLICK)
    def test_click_purchase_redirects_to_click(self):
        response = self.client.post(reverse("wallet:buy"), {"coins": "20", "provider": "click"})
        order = PaymentOrder.objects.get()
        self.assertEqual(order.amount_uzs, 200_000)
        self.assertTrue(response.url.startswith("https://my.click.uz/services/pay?"))
        self.assertIn("service_id=111", response.url)
        self.assertIn("merchant_id=222", response.url)
        self.assertIn("amount=200000", response.url)
        self.assertIn(f"transaction_param={order.pk}", response.url)

    @override_settings(PAYME=NOT_CONFIGURED, CLICK=NOT_CONFIGURED_CLICK)
    def test_unconfigured_provider_does_not_crash_or_create_orders(self):
        response = self.client.post(reverse("wallet:buy"), {"coins": "10", "provider": "payme"})
        self.assertRedirects(response, "/freelancer/dashboard/?tab=store", fetch_redirect_response=False)
        self.assertFalse(PaymentOrder.objects.exists())
        follow = self.client.get(response.url)
        self.assertContains(follow, "hozircha mavjud emas")

    @override_settings(PAYME=PAYME, CLICK=CLICK)
    def test_unknown_package_or_provider_is_refused(self):
        for data in ({"coins": "7", "provider": "payme"}, {"coins": "10", "provider": "paypal"}, {"provider": "payme"}):
            with self.subTest(data=data):
                response = self.client.post(reverse("wallet:buy"), data)
                self.assertEqual(response.status_code, 302)
        self.assertFalse(PaymentOrder.objects.exists())

    @override_settings(PAYME=PAYME, CLICK=CLICK)
    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(reverse("wallet:buy")).status_code, 405)

    @override_settings(PAYME=PAYME, CLICK=CLICK)
    def test_client_account_cannot_buy_coins(self):
        client_user = User.objects.create_user(phone="+998907654321", first_name="C", last_name="D", role=User.Role.USER)
        self.client.force_login(client_user)
        response = self.client.post(reverse("wallet:buy"), {"coins": "10", "provider": "payme"})
        self.assertEqual(response.status_code, 404)
