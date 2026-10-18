from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from architects.models import ArchitectProfile
from wallet.models import PaymentOrder, Wallet


def make_staff():
    return User.objects.create_superuser(phone="+998900000001", password="x", first_name="Admin", last_name="A")


def make_paid_order(architect, coins=10, amount=100_000, when=None):
    wallet, _ = Wallet.objects.get_or_create(architect=architect)
    order = PaymentOrder.objects.create(
        wallet=wallet, provider=PaymentOrder.Provider.PAYME, coins=coins, amount_uzs=amount,
        status=PaymentOrder.Status.PAID,
    )
    if when is not None:
        PaymentOrder.objects.filter(pk=order.pk).update(paid_at=when)
    else:
        PaymentOrder.objects.filter(pk=order.pk).update(paid_at=timezone.now())
    return order


class RevenueDashboardTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        user = User.objects.create_user(phone="+998901111111", first_name="Ar", last_name="X", role=User.Role.ARCHITECT)
        self.architect = ArchitectProfile.objects.create(user=user)
        self.client.force_login(self.staff)

    def test_requires_staff(self):
        self.client.logout()
        response = self.client.get(reverse("revenue_dashboard"))
        self.assertNotEqual(response.status_code, 200)

    def test_only_paid_orders_count(self):
        make_paid_order(self.architect, amount=50_000)
        wallet = Wallet.objects.get(architect=self.architect)
        PaymentOrder.objects.create(
            wallet=wallet, provider=PaymentOrder.Provider.CLICK, coins=5, amount_uzs=999_999,
            status=PaymentOrder.Status.CREATED,  # never paid — must be excluded
        )
        page = self.client.get(reverse("revenue_dashboard"))
        self.assertEqual(page.context["summary"]["all_time"]["revenue"], 50_000)
        self.assertEqual(page.context["summary"]["all_time"]["orders"], 1)

    def test_today_total_excludes_older_payments(self):
        make_paid_order(self.architect, amount=10_000, when=timezone.now())
        make_paid_order(self.architect, amount=20_000, when=timezone.now() - timezone.timedelta(days=40))
        page = self.client.get(reverse("revenue_dashboard"))
        self.assertEqual(page.context["summary"]["today"]["revenue"], 10_000)
        self.assertEqual(page.context["summary"]["all_time"]["revenue"], 30_000)

    def test_page_renders_with_no_payments_at_all(self):
        page = self.client.get(reverse("revenue_dashboard"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Hali to'lov yo'q.")
