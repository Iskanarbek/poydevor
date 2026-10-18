"""Click Shop API (prepare / complete) — https://docs.click.uz

Click calls two endpoints with form-encoded data and signs every call with an
MD5 hash of its fields plus our secret key. Like the Payme module, this one
always answers with a JSON body (never raises) and is inert until the CLICK_*
credentials are configured.

The order being paid is identified by ``merchant_trans_id``: the id of a
``PaymentOrder``. Amounts are in UZS.
"""
import hashlib
import hmac
import logging
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction

from wallet.models import ClickTransaction, PaymentOrder
from wallet.payments.config import click_config, click_enabled
from wallet.services import credit_order

logger = logging.getLogger(__name__)

ACTION_PREPARE = "0"
ACTION_COMPLETE = "1"

ERR_OK = 0
ERR_SIGN = -1
ERR_AMOUNT = -2
ERR_ACTION = -3
ERR_ALREADY_PAID = -4
ERR_ORDER_NOT_FOUND = -5
ERR_TRANSACTION_NOT_FOUND = -6
ERR_UPDATE_FAILED = -7
ERR_BAD_REQUEST = -8
ERR_CANCELLED = -9

NOTES = {
    ERR_OK: "Success",
    ERR_SIGN: "SIGN CHECK FAILED!",
    ERR_AMOUNT: "Incorrect parameter amount",
    ERR_ACTION: "Action not found",
    ERR_ALREADY_PAID: "Already paid",
    ERR_ORDER_NOT_FOUND: "Order not found",
    ERR_TRANSACTION_NOT_FOUND: "Transaction does not exist",
    ERR_UPDATE_FAILED: "Failed to update user",
    ERR_BAD_REQUEST: "Error in request from click",
    ERR_CANCELLED: "Transaction cancelled",
}

PREPARE_FIELDS = (
    "click_trans_id", "service_id", "merchant_trans_id", "amount", "action", "sign_time", "sign_string",
)
COMPLETE_FIELDS = PREPARE_FIELDS + ("merchant_prepare_id",)


def _response(post, code: int, **extra) -> dict:
    body = {
        "click_trans_id": post.get("click_trans_id"),
        "merchant_trans_id": post.get("merchant_trans_id"),
        "error": code,
        "error_note": NOTES[code],
    }
    body.update(extra)
    return body


def _signature(post, *, complete: bool) -> str:
    parts = [
        post.get("click_trans_id", ""),
        post.get("service_id", ""),
        click_config().get("SECRET_KEY", ""),
        post.get("merchant_trans_id", ""),
    ]
    if complete:
        parts.append(post.get("merchant_prepare_id", ""))
    parts += [post.get("amount", ""), post.get("action", ""), post.get("sign_time", "")]
    return hashlib.md5("".join(parts).encode()).hexdigest()


def _check_request(post, *, complete: bool):
    """Validate a call from Click. Returns ``(order, None)`` or ``(None, error_code)``."""
    if not click_enabled():
        return None, ERR_SIGN
    required = COMPLETE_FIELDS if complete else PREPARE_FIELDS
    if any(post.get(field) in (None, "") for field in required):
        return None, ERR_BAD_REQUEST
    if post.get("service_id") != click_config()["SERVICE_ID"]:
        return None, ERR_BAD_REQUEST
    expected = _signature(post, complete=complete)
    if not hmac.compare_digest(expected, post.get("sign_string", "").lower()):
        return None, ERR_SIGN
    if post.get("action") != (ACTION_COMPLETE if complete else ACTION_PREPARE):
        return None, ERR_ACTION
    try:
        order = PaymentOrder.objects.filter(
            pk=int(post["merchant_trans_id"]), provider=PaymentOrder.Provider.CLICK,
        ).first()
    except ValueError:
        order = None
    if order is None:
        return None, ERR_ORDER_NOT_FOUND
    try:
        amount = Decimal(post["amount"])
    except InvalidOperation:
        return None, ERR_BAD_REQUEST
    if amount != Decimal(order.amount_uzs):
        return None, ERR_AMOUNT
    return order, None


def _reported_error(post) -> int:
    try:
        return int(post.get("error", 0))
    except ValueError:
        return 0


def prepare(post) -> dict:
    try:
        order, error = _check_request(post, complete=False)
        if error is not None:
            return _response(post, error)
        try:
            click_trans_id = int(post["click_trans_id"])
            paydoc_id = int(post["click_paydoc_id"]) if post.get("click_paydoc_id") else None
        except ValueError:
            return _response(post, ERR_BAD_REQUEST)

        with transaction.atomic():
            order = PaymentOrder.objects.select_for_update().get(pk=order.pk)
            existing = ClickTransaction.objects.filter(click_trans_id=click_trans_id).first()
            if existing is not None and existing.order_id != order.pk:
                return _response(post, ERR_BAD_REQUEST)
            if order.status == PaymentOrder.Status.PAID or (
                existing is not None and existing.status == ClickTransaction.Status.COMPLETED
            ):
                return _response(post, ERR_ALREADY_PAID)
            if order.status == PaymentOrder.Status.CANCELLED or (
                existing is not None and existing.status == ClickTransaction.Status.CANCELLED
            ):
                return _response(post, ERR_CANCELLED)
            if _reported_error(post) < 0:
                return _response(post, ERR_CANCELLED)
            if existing is None:
                try:
                    with transaction.atomic():
                        existing = ClickTransaction.objects.create(
                            click_trans_id=click_trans_id, click_paydoc_id=paydoc_id,
                            order=order, amount=Decimal(post["amount"]),
                        )
                except IntegrityError:
                    existing = ClickTransaction.objects.get(click_trans_id=click_trans_id)
            return _response(post, ERR_OK, merchant_prepare_id=existing.pk)
    except Exception:  # noqa: BLE001 — Click must always get a JSON answer
        logger.exception("Unexpected error while handling a Click prepare request")
        return _response(post, ERR_UPDATE_FAILED)


def complete(post) -> dict:
    try:
        order, error = _check_request(post, complete=True)
        if error is not None:
            return _response(post, error)
        try:
            click_trans_id = int(post["click_trans_id"])
            prepare_id = int(post["merchant_prepare_id"])
        except ValueError:
            return _response(post, ERR_BAD_REQUEST)

        with transaction.atomic():
            tx = ClickTransaction.objects.select_for_update().filter(
                pk=prepare_id, order=order, click_trans_id=click_trans_id,
            ).first()
            if tx is None:
                return _response(post, ERR_TRANSACTION_NOT_FOUND)
            if tx.status == ClickTransaction.Status.COMPLETED:
                return _response(post, ERR_ALREADY_PAID)
            if tx.status == ClickTransaction.Status.CANCELLED:
                return _response(post, ERR_CANCELLED)
            if _reported_error(post) < 0:
                tx.status = ClickTransaction.Status.CANCELLED
                tx.save(update_fields=["status"])
                PaymentOrder.objects.filter(pk=order.pk, status=PaymentOrder.Status.CREATED).update(
                    status=PaymentOrder.Status.CANCELLED,
                )
                return _response(post, ERR_CANCELLED)
            credit_order(order)
            tx.status = ClickTransaction.Status.COMPLETED
            tx.save(update_fields=["status"])
            return _response(post, ERR_OK, merchant_confirm_id=tx.pk)
    except Exception:  # noqa: BLE001 — Click must always get a JSON answer
        logger.exception("Unexpected error while handling a Click complete request")
        return _response(post, ERR_UPDATE_FAILED)
