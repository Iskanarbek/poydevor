import hashlib

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from architects.models import ArchitectProfile
from wallet.models import ClickTransaction, CoinTransaction, PaymentOrder, Wallet

CLICK = {"SERVICE_ID": "111", "MERCHANT_ID": "222", "SECRET_KEY": "click-secret"}


def sign(fields, secret="click-secret", *, complete=False):
    parts = [fields["click_trans_id"], fields["service_id"], secret, fields["merchant_trans_id"]]
    if complete:
        parts.append(str(fields["merchant_prepare_id"]))
    parts += [fields["amount"], fields["action"], fields["sign_time"]]
    return hashlib.md5("".join(str(p) for p in parts).encode()).hexdigest()


@override_settings(CLICK=CLICK)
class ClickTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user(phone="+998901234567", first_name="N", last_name="Y", role=User.Role.ARCHITECT)
        self.profile = ArchitectProfile.objects.create(user=user, bio="x")
        self.wallet = Wallet.objects.create(architect=self.profile)
        self.order = PaymentOrder.objects.create(wallet=self.wallet, provider="click", coins=10, amount_uzs=100_000)

    def fields(self, step, **overrides):
        data = {
            "click_trans_id": "5001", "service_id": "111", "click_paydoc_id": "9001",
            "merchant_trans_id": str(self.order.pk), "amount": "100000.0", "action": str(step),
            "error": "0", "error_note": "Success", "sign_time": "2026-09-20 12:00:00",
        }
        data.update(overrides)
        return data

    def prepare(self, secret="click-secret", **overrides):
        data = self.fields(0, **overrides)
        data["sign_string"] = overrides.get("sign_string") or sign(data, secret)
        response = self.client.post(reverse("wallet:click_prepare"), data)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def complete(self, prepare_id, secret="click-secret", **overrides):
        data = self.fields(1, merchant_prepare_id=str(prepare_id), **overrides)
        data["sign_string"] = overrides.get("sign_string") or sign(data, secret, complete=True)
        response = self.client.post(reverse("wallet:click_complete"), data)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def balance(self):
        self.wallet.refresh_from_db()
        return self.wallet.balance


class ClickFlowTests(ClickTestCase):
    def test_prepare_then_complete_credits_coins_once(self):
        prepared = self.prepare()
        self.assertEqual(prepared["error"], 0)
        self.assertEqual(prepared["merchant_trans_id"], str(self.order.pk))
        self.assertEqual(self.balance(), 0)

        done = self.complete(prepared["merchant_prepare_id"])
        self.assertEqual(done["error"], 0)
        self.assertIn("merchant_confirm_id", done)
        self.assertEqual(self.balance(), 10)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PaymentOrder.Status.PAID)

        # Click retrying Complete is reported as already paid; no double credit.
        self.assertEqual(self.complete(prepared["merchant_prepare_id"])["error"], -4)
        self.assertEqual(self.balance(), 10)
        self.assertEqual(CoinTransaction.objects.filter(order=self.order).count(), 1)

    def test_prepare_is_idempotent(self):
        first = self.prepare()
        second = self.prepare()
        self.assertEqual(first["merchant_prepare_id"], second["merchant_prepare_id"])
        self.assertEqual(ClickTransaction.objects.count(), 1)

    def test_prepare_after_payment_reports_already_paid(self):
        self.complete(self.prepare()["merchant_prepare_id"])
        self.assertEqual(self.prepare(click_trans_id="5002")["error"], -4)

    def test_click_reported_failure_cancels_without_crediting(self):
        prepared = self.prepare()
        done = self.complete(prepared["merchant_prepare_id"], error="-5017")
        self.assertEqual(done["error"], -9)
        self.assertEqual(self.balance(), 0)
        self.assertEqual(ClickTransaction.objects.get().status, ClickTransaction.Status.CANCELLED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PaymentOrder.Status.CANCELLED)
        self.assertEqual(self.complete(prepared["merchant_prepare_id"])["error"], -9)


class ClickValidationTests(ClickTestCase):
    def test_bad_signature(self):
        self.assertEqual(self.prepare(secret="wrong")["error"], -1)
        prepared = self.prepare()
        self.assertEqual(self.complete(prepared["merchant_prepare_id"], secret="wrong")["error"], -1)
        self.assertEqual(self.balance(), 0)

    def test_tampered_amount_fails_signature_and_wrong_amount_fails_check(self):
        data = self.fields(0)
        data["sign_string"] = sign(data)
        data["amount"] = "1.0"  # changed after signing
        self.assertEqual(self.client.post(reverse("wallet:click_prepare"), data).json()["error"], -1)
        # A correctly signed request for the wrong amount is rejected too.
        self.assertEqual(self.prepare(amount="50000.0")["error"], -2)
        self.assertFalse(ClickTransaction.objects.exists())

    def test_unknown_order(self):
        self.assertEqual(self.prepare(merchant_trans_id="999999")["error"], -5)
        self.assertEqual(self.prepare(merchant_trans_id="abc")["error"], -5)

    def test_order_of_another_provider_is_unknown(self):
        self.order.provider = "payme"
        self.order.save()
        self.assertEqual(self.prepare()["error"], -5)

    def test_wrong_action(self):
        self.assertEqual(self.prepare(action="1")["error"], -3)

    def test_unknown_prepare_id(self):
        self.assertEqual(self.complete(424242)["error"], -6)

    def test_wrong_service_id(self):
        self.assertEqual(self.prepare(service_id="999")["error"], -8)

    def test_missing_fields_and_bad_numbers_are_request_errors_not_crashes(self):
        response = self.client.post(reverse("wallet:click_prepare"), {"click_trans_id": "1"})
        self.assertEqual(response.json()["error"], -8)
        self.assertEqual(self.prepare(amount="lots")["error"], -8)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(reverse("wallet:click_prepare")).status_code, 405)
        self.assertEqual(self.client.get(reverse("wallet:click_complete")).status_code, 405)

    @override_settings(CLICK={"SERVICE_ID": "", "MERCHANT_ID": "", "SECRET_KEY": ""})
    def test_unconfigured_click_refuses_everything(self):
        data = self.fields(0, service_id="")
        data["sign_string"] = sign(data, secret="")
        response = self.client.post(reverse("wallet:click_prepare"), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error"], -1)
        self.assertEqual(self.balance(), 0)
