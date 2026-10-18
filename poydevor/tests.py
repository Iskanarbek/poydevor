from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from architects.models import ArchitectProfile
from wallet.models import Wallet


class ArchitectWalletContextProcessorTests(TestCase):
    def test_architect_with_wallet_gets_wallet_in_context(self):
        user = User.objects.create_user(
            phone="+998901112233", password="testpass123",
            first_name="Aziz", last_name="Karimov", role=User.Role.ARCHITECT,
        )
        profile = ArchitectProfile.objects.create(user=user, bio="Bio")
        Wallet.objects.create(architect=profile, balance=980)

        self.client.login(phone="+998901112233", password="testpass123")
        response = self.client.get(reverse("architects:freelancer_dashboard"))

        self.assertIn("architect_wallet", response.context)
        self.assertEqual(response.context["architect_wallet"].balance, 980)
        self.assertContains(response, "980")

    def test_architect_without_wallet_gets_empty_context(self):
        user = User.objects.create_user(
            phone="+998901112234", password="testpass123",
            first_name="Aziz", last_name="Karimov", role=User.Role.ARCHITECT,
        )
        ArchitectProfile.objects.create(user=user, bio="Bio")

        self.client.login(phone="+998901112234", password="testpass123")
        response = self.client.get(reverse("architects:freelancer_dashboard"))

        self.assertNotIn("architect_wallet", response.context)

    def test_regular_user_gets_empty_context(self):
        User.objects.create_user(
            phone="+998901112235", password="testpass123",
            first_name="Nodira", last_name="Yusupova", role=User.Role.USER,
        )
        self.client.login(phone="+998901112235", password="testpass123")
        response = self.client.get(reverse("applications:dashboard"))

        self.assertNotIn("architect_wallet", response.context)

    def test_anonymous_visitor_gets_empty_context_no_error(self):
        response = self.client.get(reverse("architects:list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("architect_wallet", response.context)
