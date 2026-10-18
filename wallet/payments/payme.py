"""Payme Merchant API (JSON-RPC 2.0) — https://developer.help.paycom.uz

One endpoint receives every call from Payme. Whatever goes wrong, this module
answers with a well-formed JSON-RPC response (HTTP 200) instead of raising, and
it stays completely inert until PAYME_MERCHANT_ID and PAYME_KEY are configured.

The order a customer pays is identified by ``account.order_id``: the id of a
``PaymentOrder``. Amounts arrive in tiyin (1 UZS = 100 tiyin).
"""
import base64
import hmac
import json
import logging
import time

from django.db import IntegrityError, transaction

from wallet.models import PaymeTransaction, PaymentOrder
from wallet.payments.config import payme_config, payme_enabled
from wallet.services import CannotRefundError, credit_order, refund_order

logger = logging.getLogger(__name__)

# Transaction states
STATE_CREATED = 1
STATE_PERFORMED = 2
STATE_CANCELLED = -1
STATE_CANCELLED_AFTER_PERFORM = -2

# Payme cancels an unpaid transaction after 12 hours.
TIMEOUT_MS = 12 * 60 * 60 * 1000
REASON_TIMEOUT = 4

# Error codes
ERR_TRANSPORT = -32300
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_AUTH = -32504
ERR_SYSTEM = -32400
ERR_WRONG_AMOUNT = -31001
ERR_TRANSACTION_NOT_FOUND = -31003
ERR_CANNOT_CANCEL = -31007
ERR_CANNOT_PERFORM = -31008
ERR_ORDER_NOT_FOUND = -31050
ERR_ORDER_UNAVAILABLE = -31051
ERR_ORDER_BUSY = -31099

MESSAGES = {
    ERR_TRANSPORT: ("So'rov POST bo'lishi kerak", "Запрос должен быть POST", "Request must be POST"),
    ERR_PARSE: ("JSON xato", "Ошибка разбора JSON", "JSON parse error"),
    ERR_INVALID_REQUEST: ("Noto'g'ri so'rov", "Неверный запрос", "Invalid request"),
    ERR_METHOD_NOT_FOUND: ("Metod topilmadi", "Метод не найден", "Method not found"),
    ERR_AUTH: ("Ruxsat yo'q", "Недостаточно привилегий", "Insufficient privilege to perform this method"),
    ERR_SYSTEM: ("Tizim xatosi", "Системная ошибка", "System error"),
    ERR_WRONG_AMOUNT: ("Noto'g'ri summa", "Неверная сумма", "Wrong amount"),
    ERR_TRANSACTION_NOT_FOUND: ("Tranzaksiya topilmadi", "Транзакция не найдена", "Transaction not found"),
    ERR_CANNOT_CANCEL: (
        "Tranzaksiyani bekor qilib bo'lmaydi", "Невозможно отменить транзакцию", "Unable to cancel the transaction",
    ),
    ERR_CANNOT_PERFORM: (
        "Operatsiyani bajarib bo'lmaydi", "Невозможно выполнить операцию", "Unable to perform the operation",
    ),
    ERR_ORDER_NOT_FOUND: ("Buyurtma topilmadi", "Заказ не найден", "Order not found"),
    ERR_ORDER_UNAVAILABLE: (
        "Buyurtma to'langan yoki bekor qilingan", "Заказ оплачен или отменён", "Order is already paid or cancelled",
    ),
    ERR_ORDER_BUSY: (
        "Buyurtma bo'yicha boshqa tranzaksiya kutilmoqda",
        "По заказу ожидается другая транзакция",
        "Another transaction is pending for this order",
    ),
}


class PaymeError(Exception):
    def __init__(self, code: int, data=None):
        super().__init__(code)
        self.code = code
        self.data = data


def _now_ms() -> int:
    return int(time.time() * 1000)


def _error_response(code: int, request_id, data=None) -> dict:
    uz, ru, en = MESSAGES[code]
    error = {"code": code, "message": {"uz": uz, "ru": ru, "en": en}}
    if data is not None:
        error["data"] = data
    return {"error": error, "id": request_id}


def _authorized(request) -> bool:
    if not payme_enabled():
        return False
    scheme, _, token = request.META.get("HTTP_AUTHORIZATION", "").partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        decoded = base64.b64decode(token.strip(), validate=True).decode()
    except (ValueError, UnicodeDecodeError):
        return False
    login, _, key = decoded.partition(":")
    return login == "Paycom" and hmac.compare_digest(key.encode(), payme_config()["KEY"].encode())


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _find_order(params: dict, *, lock: bool = False) -> PaymentOrder:
    account = params.get("account")
    raw = account.get("order_id") if isinstance(account, dict) else None
    try:
        if isinstance(raw, bool) or not isinstance(raw, (int, str)):
            raise ValueError
        order_pk = int(raw)
    except ValueError:
        raise PaymeError(ERR_ORDER_NOT_FOUND, data="order_id")
    queryset = PaymentOrder.objects.filter(pk=order_pk, provider=PaymentOrder.Provider.PAYME)
    if lock:
        queryset = queryset.select_for_update()
    order = queryset.first()
    if order is None:
        raise PaymeError(ERR_ORDER_NOT_FOUND, data="order_id")
    return order


def _validate_order(order: PaymentOrder, params: dict) -> None:
    amount = params.get("amount")
    if not _is_int(amount) or amount != order.amount_tiyin:
        raise PaymeError(ERR_WRONG_AMOUNT)
    if order.status != PaymentOrder.Status.CREATED:
        raise PaymeError(ERR_ORDER_UNAVAILABLE, data="order_id")


def _find_transaction(params: dict, *, lock: bool = False) -> PaymeTransaction:
    payme_id = params.get("id")
    queryset = PaymeTransaction.objects.filter(payme_id=payme_id) if isinstance(payme_id, str) else None
    if queryset is None:
        raise PaymeError(ERR_TRANSACTION_NOT_FOUND)
    if lock:
        queryset = queryset.select_for_update()
    tx = queryset.first()
    if tx is None:
        raise PaymeError(ERR_TRANSACTION_NOT_FOUND)
    return tx


def _expired(tx: PaymeTransaction) -> bool:
    return _now_ms() - tx.create_time > TIMEOUT_MS


def _cancel_unpaid(tx: PaymeTransaction, reason) -> None:
    """Cancel a transaction that was never paid (call inside a transaction)."""
    tx.state = STATE_CANCELLED
    tx.reason = reason
    tx.cancel_time = _now_ms()
    tx.save(update_fields=["state", "reason", "cancel_time"])
    PaymentOrder.objects.filter(pk=tx.order_id, status=PaymentOrder.Status.CREATED).update(
        status=PaymentOrder.Status.CANCELLED,
    )


def _create_result(tx: PaymeTransaction) -> dict:
    return {"create_time": tx.create_time, "transaction": str(tx.pk), "state": tx.state}


def _perform_result(tx: PaymeTransaction) -> dict:
    return {"transaction": str(tx.pk), "perform_time": tx.perform_time, "state": tx.state}


def _cancel_result(tx: PaymeTransaction) -> dict:
    return {"transaction": str(tx.pk), "cancel_time": tx.cancel_time, "state": tx.state}


# --- API methods ---------------------------------------------------------


def check_perform_transaction(params: dict) -> dict:
    order = _find_order(params)
    _validate_order(order, params)
    return {"allow": True}


def create_transaction(params: dict) -> dict:
    payme_id, payme_time = params.get("id"), params.get("time")
    if not isinstance(payme_id, str) or not payme_id or not _is_int(payme_time):
        raise PaymeError(ERR_INVALID_REQUEST)

    expired = False
    with transaction.atomic():
        existing = PaymeTransaction.objects.select_for_update().filter(payme_id=payme_id).first()
        if existing is not None:
            if existing.state != STATE_CREATED:
                raise PaymeError(ERR_CANNOT_PERFORM)
            if not _expired(existing):
                return _create_result(existing)
            _cancel_unpaid(existing, REASON_TIMEOUT)
            expired = True
        else:
            order = _find_order(params, lock=True)
            _validate_order(order, params)
            if order.payme_transactions.filter(state=STATE_CREATED).exists():
                raise PaymeError(ERR_ORDER_BUSY, data="order_id")
            try:
                with transaction.atomic():
                    tx = PaymeTransaction.objects.create(
                        payme_id=payme_id, order=order, amount=order.amount_tiyin,
                        state=STATE_CREATED, payme_time=payme_time, create_time=_now_ms(),
                    )
            except IntegrityError:
                # The same Payme id arrived twice at once; answer like a retry.
                tx = PaymeTransaction.objects.get(payme_id=payme_id)
            return _create_result(tx)
    if expired:
        raise PaymeError(ERR_CANNOT_PERFORM)


def perform_transaction(params: dict) -> dict:
    expired = False
    with transaction.atomic():
        tx = _find_transaction(params, lock=True)
        if tx.state == STATE_PERFORMED:
            return _perform_result(tx)
        if tx.state != STATE_CREATED:
            raise PaymeError(ERR_CANNOT_PERFORM)
        if _expired(tx):
            _cancel_unpaid(tx, REASON_TIMEOUT)
            expired = True
        else:
            credit_order(tx.order)
            tx.state = STATE_PERFORMED
            tx.perform_time = _now_ms()
            tx.save(update_fields=["state", "perform_time"])
            return _perform_result(tx)
    if expired:
        raise PaymeError(ERR_CANNOT_PERFORM)


def cancel_transaction(params: dict) -> dict:
    reason = params.get("reason")
    reason = reason if _is_int(reason) else None
    with transaction.atomic():
        tx = _find_transaction(params, lock=True)
        if tx.state == STATE_CREATED:
            _cancel_unpaid(tx, reason)
        elif tx.state == STATE_PERFORMED:
            try:
                refund_order(tx.order)
            except CannotRefundError:
                raise PaymeError(ERR_CANNOT_CANCEL)
            tx.state = STATE_CANCELLED_AFTER_PERFORM
            tx.reason = reason
            tx.cancel_time = _now_ms()
            tx.save(update_fields=["state", "reason", "cancel_time"])
        return _cancel_result(tx)


def check_transaction(params: dict) -> dict:
    tx = _find_transaction(params)
    return {
        "create_time": tx.create_time,
        "perform_time": tx.perform_time,
        "cancel_time": tx.cancel_time,
        "transaction": str(tx.pk),
        "state": tx.state,
        "reason": tx.reason,
    }


def get_statement(params: dict) -> dict:
    start, end = params.get("from"), params.get("to")
    if not _is_int(start) or not _is_int(end):
        raise PaymeError(ERR_INVALID_REQUEST)
    transactions = PaymeTransaction.objects.filter(
        payme_time__gte=start, payme_time__lte=end,
    ).order_by("payme_time")
    return {"transactions": [
        {
            "id": tx.payme_id,
            "time": tx.payme_time,
            "amount": tx.amount,
            "account": {"order_id": str(tx.order_id)},
            "create_time": tx.create_time,
            "perform_time": tx.perform_time,
            "cancel_time": tx.cancel_time,
            "transaction": str(tx.pk),
            "state": tx.state,
            "reason": tx.reason,
        }
        for tx in transactions
    ]}


METHODS = {
    "CheckPerformTransaction": check_perform_transaction,
    "CreateTransaction": create_transaction,
    "PerformTransaction": perform_transaction,
    "CancelTransaction": cancel_transaction,
    "CheckTransaction": check_transaction,
    "GetStatement": get_statement,
}


def handle(request) -> dict:
    """Turn one HTTP request from Payme into a JSON-RPC response dict."""
    request_id = None
    try:
        if request.method != "POST":
            return _error_response(ERR_TRANSPORT, request_id)
        try:
            payload = json.loads(request.body)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            request_id = payload.get("id")
        if not _authorized(request):
            return _error_response(ERR_AUTH, request_id)
        if payload is None:
            return _error_response(ERR_PARSE, request_id)
        if not isinstance(payload, dict):
            return _error_response(ERR_INVALID_REQUEST, request_id)
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            return _error_response(ERR_INVALID_REQUEST, request_id)
        method = METHODS.get(payload.get("method"))
        if method is None:
            return _error_response(ERR_METHOD_NOT_FOUND, request_id)
        return {"result": method(params), "id": request_id}
    except PaymeError as error:
        return _error_response(error.code, request_id, error.data)
    except Exception:  # noqa: BLE001 — Payme must always get a JSON answer
        logger.exception("Unexpected error while handling a Payme request")
        return _error_response(ERR_SYSTEM, request_id)
