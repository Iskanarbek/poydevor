import base64
import json
import time

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from architects.models import ArchitectProfile
from wallet.models import CoinTransaction, PaymentOrder, PaymeTransaction, Wallet
from wallet.payments import payme

PAYME = {"MERCHANT_ID": "merchant-1", "KEY": "payme-secret", "TEST_MODE": True}
AUTH = "Basic " + base64.b64encode(b"Paycom:payme-secret").decode()


@override_settings(PAYME=PAYME)
class PaymeTestCase(TestCase):
    def setUp(self):
        user = User.objects.create_user(phone="+998901234567", first_name="N", last_name="Y", role=User.Role.ARCHITECT)
        self.profile = ArchitectProfile.objects.create(user=user, bio="x")
        self.wallet = Wallet.objects.create(architect=self.profile)
        self.order = PaymentOrder.objects.create(
            wallet=self.wallet, provider="payme", coins=10, amount_uzs=100_000,
        )

    def call(self, method, params=None, *, auth=AUTH, request_id=7):
        headers = {"HTTP_AUTHORIZATION": auth} if auth else {}
        response = self.client.post(
            reverse("wallet:payme_webhook"),
            data=json.dumps({"id": request_id, "method": method, "params": params or {}}),
            content_type="application/json", **headers,
        )
        self.assertEqual(response.status_code, 200)  # Payme always gets HTTP 200
        return response.json()

    def account(self, **overrides):
        return {"amount": 10_000_000, "account": {"order_id": str(self.order.pk)}, **overrides}

    def create(self, payme_id="tx-1", **overrides):
        return self.call("CreateTransaction", {"id": payme_id, "time": 1_700_000_000_000, **self.account(**overrides)})

    def assertError(self, body, code):
        self.assertIn("error", body, body)
        self.assertEqual(body["error"]["code"], code, body)

    def balance(self):
        self.wallet.refresh_from_db()
        return self.wallet.balance


class PaymeAuthTests(PaymeTestCase):
    def test_missing_or_wrong_credentials_are_refused(self):
        wrong_key = "Basic " + base64.b64encode(b"Paycom:nope").decode()
        wrong_login = "Basic " + base64.b64encode(b"Someone:payme-secret").decode()
        for auth in (None, "Basic", "Basic !!!", wrong_key, wrong_login, "Bearer payme-secret"):
            with self.subTest(auth=auth):
                body = self.call("CheckPerformTransaction", self.account(), auth=auth)
                self.assertError(body, -32504)
                self.assertEqual(body["id"], 7)

    @override_settings(PAYME={"MERCHANT_ID": "", "KEY": "", "TEST_MODE": False})
    def test_unconfigured_payme_refuses_everything_even_an_empty_key(self):
        empty_key = "Basic " + base64.b64encode(b"Paycom:").decode()
        self.assertError(self.call("CheckPerformTransaction", self.account(), auth=empty_key), -32504)
        self.assertEqual(self.balance(), 0)

    def test_malformed_requests_get_json_errors_not_crashes(self):
        url = reverse("wallet:payme_webhook")
        self.assertError(self.client.get(url).json(), -32300)
        bad_json = self.client.post(url, data="{oops", content_type="application/json", HTTP_AUTHORIZATION=AUTH)
        self.assertError(bad_json.json(), -32700)
        as_list = self.client.post(url, data="[1]", content_type="application/json", HTTP_AUTHORIZATION=AUTH)
        self.assertError(as_list.json(), -32600)
        self.assertError(self.call("NoSuchMethod"), -32601)
        self.assertError(self.call("CheckPerformTransaction", {"account": None}), -31050)

    def test_unexpected_internal_error_becomes_system_error(self):
        from unittest.mock import patch
        with patch.dict(payme.METHODS, {"CheckTransaction": lambda params: 1 / 0}):
            with self.assertLogs("wallet.payments.payme", level="ERROR"):
                self.assertError(self.call("CheckTransaction", {"id": "x"}), -32400)


class PaymeCheckPerformTests(PaymeTestCase):
    def test_valid_order_is_allowed(self):
        self.assertEqual(self.call("CheckPerformTransaction", self.account())["result"], {"allow": True})

    def test_wrong_amount(self):
        self.assertError(self.call("CheckPerformTransaction", self.account(amount=5_000_000)), -31001)
        self.assertError(self.call("CheckPerformTransaction", self.account(amount="10000000")), -31001)

    def test_unknown_or_foreign_order(self):
        self.assertError(self.call("CheckPerformTransaction", {"amount": 1, "account": {"order_id": "999999"}}), -31050)
        self.assertError(self.call("CheckPerformTransaction", {"amount": 1, "account": {"order_id": "abc"}}), -31050)
        click_order = PaymentOrder.objects.create(wallet=self.wallet, provider="click", coins=10, amount_uzs=100_000)
        self.assertError(
            self.call("CheckPerformTransaction", {"amount": 10_000_000, "account": {"order_id": str(click_order.pk)}}),
            -31050,
        )

    def test_paid_order_is_unavailable(self):
        self.order.status = PaymentOrder.Status.PAID
        self.order.save()
        self.assertError(self.call("CheckPerformTransaction", self.account()), -31051)


class PaymeLifecycleTests(PaymeTestCase):
    def test_full_payment_credits_coins_exactly_once(self):
        created = self.create()["result"]
        self.assertEqual(created["state"], 1)
        self.assertEqual(self.balance(), 0)

        performed = self.call("PerformTransaction", {"id": "tx-1"})["result"]
        self.assertEqual(performed["state"], 2)
        self.assertEqual(performed["transaction"], created["transaction"])
        self.assertEqual(self.balance(), 10)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PaymentOrder.Status.PAID)

        # Payme retrying Perform must not add coins again.
        again = self.call("PerformTransaction", {"id": "tx-1"})["result"]
        self.assertEqual(again["perform_time"], performed["perform_time"])
        self.assertEqual(self.balance(), 10)
        self.assertEqual(CoinTransaction.objects.filter(order=self.order).count(), 1)

    def test_create_is_idempotent(self):
        first = self.create()["result"]
        second = self.create()["result"]
        self.assertEqual(first, second)
        self.assertEqual(PaymeTransaction.objects.count(), 1)

    def test_second_transaction_for_same_order_is_refused(self):
        self.create("tx-1")
        self.assertError(self.create("tx-2"), -31099)

    def test_create_validates_order_and_amount(self):
        self.assertError(self.create(amount=1), -31001)
        self.assertError(self.create(account={"order_id": "999999"}), -31050)
        self.assertFalse(PaymeTransaction.objects.exists())

    def test_perform_unknown_transaction(self):
        self.assertError(self.call("PerformTransaction", {"id": "ghost"}), -31003)
        self.assertError(self.call("PerformTransaction", {}), -31003)

    def test_cancel_before_payment(self):
        self.create()
        cancelled = self.call("CancelTransaction", {"id": "tx-1", "reason": 3})["result"]
        self.assertEqual(cancelled["state"], -1)
        self.assertEqual(self.balance(), 0)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, PaymentOrder.Status.CANCELLED)
        # A cancelled transaction can neither be performed nor re-created.
        self.assertError(self.call("PerformTransaction", {"id": "tx-1"}), -31008)
        self.assertError(self.create(), -31008)
        # Cancelling twice is answered, not an error.
        self.assertEqual(self.call("CancelTransaction", {"id": "tx-1", "reason": 3})["result"]["state"], -1)

    def test_refund_after_payment_takes_coins_back(self):
        self.create()
        self.call("PerformTransaction", {"id": "tx-1"})
        result = self.call("CancelTransaction", {"id": "tx-1", "reason": 5})["result"]
        self.assertEqual(result["state"], -2)
        self.assertEqual(self.balance(), 0)
        self.assertEqual(self.call("CancelTransaction", {"id": "tx-1", "reason": 5})["result"]["state"], -2)
        self.assertEqual(self.balance(), 0)  # not deducted twice
        self.assertEqual(
            CoinTransaction.objects.filter(order=self.order, reason=CoinTransaction.Reason.PAYMENT_REFUND).count(), 1,
        )

    def test_refund_refused_when_coins_are_already_spent(self):
        self.create()
        self.call("PerformTransaction", {"id": "tx-1"})
        Wallet.objects.filter(pk=self.wallet.pk).update(balance=4)  # spent on projects
        self.assertError(self.call("CancelTransaction", {"id": "tx-1", "reason": 5}), -31007)
        self.assertEqual(self.balance(), 4)
        self.assertEqual(PaymeTransaction.objects.get().state, 2)

    def test_check_transaction(self):
        self.create()
        body = self.call("CheckTransaction", {"id": "tx-1"})["result"]
        self.assertEqual((body["state"], body["perform_time"], body["cancel_time"], body["reason"]), (1, 0, 0, None))
        self.assertError(self.call("CheckTransaction", {"id": "ghost"}), -31003)

    def test_expired_transaction_is_cancelled_instead_of_paid(self):
        self.create()
        PaymeTransaction.objects.update(create_time=int(time.time() * 1000) - payme.TIMEOUT_MS - 1000)
        self.assertError(self.call("PerformTransaction", {"id": "tx-1"}), -31008)
        tx = PaymeTransaction.objects.get()
        self.assertEqual((tx.state, tx.reason), (-1, 4))
        self.assertEqual(self.balance(), 0)

    def test_expired_transaction_cannot_be_recreated(self):
        self.create()
        PaymeTransaction.objects.update(create_time=int(time.time() * 1000) - payme.TIMEOUT_MS - 1000)
        self.assertError(self.create(), -31008)
        self.assertEqual(PaymeTransaction.objects.get().state, -1)

    def test_get_statement(self):
        self.create()
        self.call("PerformTransaction", {"id": "tx-1"})
        body = self.call("GetStatement", {"from": 1_699_999_999_000, "to": 1_700_000_001_000})["result"]
        self.assertEqual(len(body["transactions"]), 1)
        item = body["transactions"][0]
        self.assertEqual((item["id"], item["amount"], item["state"]), ("tx-1", 10_000_000, 2))
        self.assertEqual(item["account"], {"order_id": str(self.order.pk)})
        empty = self.call("GetStatement", {"from": 0, "to": 1})["result"]
        self.assertEqual(empty["transactions"], [])
        self.assertError(self.call("GetStatement", {"from": "a", "to": 1}), -32600)
