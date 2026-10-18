from django.conf import settings
from django.db import transaction
from django.utils import timezone

from wallet.models import CoinTransaction, PaymentOrder, Wallet


class InsufficientCoinsError(Exception):
    pass


class CannotRefundError(Exception):
    """The coins from a payment were already spent, so it can't be reversed."""


def coin_price_uzs(coins: int) -> int:
    return coins * settings.COIN_PRICE_UZS


def coin_packages() -> list[dict]:
    return [
        {"coins": coins, "price_uzs": coin_price_uzs(coins), "projects": coins // settings.OFFER_COST_COINS}
        for coins in settings.COIN_PACKAGES
    ]


@transaction.atomic
def topup_coins(wallet: Wallet, amount: int) -> None:
    locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
    locked.balance += amount
    locked.save(update_fields=["balance"])
    CoinTransaction.objects.create(wallet=locked, amount=amount, reason=CoinTransaction.Reason.TOPUP)
    wallet.balance = locked.balance


@transaction.atomic
def spend_coins(wallet: Wallet, amount: int) -> None:
    locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
    if locked.balance < amount:
        raise InsufficientCoinsError("Tangalar yetarli emas")
    locked.balance -= amount
    locked.save(update_fields=["balance"])
    CoinTransaction.objects.create(wallet=locked, amount=-amount, reason=CoinTransaction.Reason.OFFER_SPEND)
    wallet.balance = locked.balance


@transaction.atomic
def refund_offer_coins(wallet: Wallet, amount: int) -> None:
    """Give back the coins an architect paid to apply to an order that no longer exists."""
    if amount <= 0:
        return
    locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
    locked.balance += amount
    locked.save(update_fields=["balance"])
    CoinTransaction.objects.create(wallet=locked, amount=amount, reason=CoinTransaction.Reason.OFFER_REFUND)
    wallet.balance = locked.balance


@transaction.atomic
def grant_signup_bonus(wallet: Wallet) -> bool:
    """Give a wallet enough coins for two projects, exactly once.

    Returns True if the bonus was granted now, False if it had been granted
    before (safe to call repeatedly, e.g. when an admin re-saves a profile).
    """
    locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
    if locked.transactions.filter(reason=CoinTransaction.Reason.SIGNUP_BONUS).exists():
        return False
    bonus = settings.SIGNUP_BONUS_COINS
    locked.balance += bonus
    locked.save(update_fields=["balance"])
    CoinTransaction.objects.create(wallet=locked, amount=bonus, reason=CoinTransaction.Reason.SIGNUP_BONUS)
    wallet.balance = locked.balance
    return True


@transaction.atomic
def credit_order(order: PaymentOrder) -> bool:
    """Add a paid order's coins to its wallet, exactly once.

    Returns True when coins were added now and False when this order had
    already been credited (a provider retrying its callback changes nothing).
    """
    order = PaymentOrder.objects.select_for_update().get(pk=order.pk)
    if order.status == PaymentOrder.Status.PAID:
        return False
    wallet = Wallet.objects.select_for_update().get(pk=order.wallet_id)
    wallet.balance += order.coins
    wallet.save(update_fields=["balance"])
    CoinTransaction.objects.create(
        wallet=wallet, amount=order.coins, reason=CoinTransaction.Reason.TOPUP, order=order,
    )
    order.status = PaymentOrder.Status.PAID
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "paid_at"])
    return True


@transaction.atomic
def refund_order(order: PaymentOrder) -> bool:
    """Take back the coins of a paid order (the provider cancelled the payment).

    Returns True when coins were removed now and False if already refunded.
    Raises ``CannotRefundError`` when the wallet no longer holds those coins.
    """
    order = PaymentOrder.objects.select_for_update().get(pk=order.pk)
    if order.status == PaymentOrder.Status.CANCELLED:
        return False
    wallet = Wallet.objects.select_for_update().get(pk=order.wallet_id)
    if wallet.balance < order.coins:
        raise CannotRefundError("Tangalar allaqachon ishlatilgan")
    wallet.balance -= order.coins
    wallet.save(update_fields=["balance"])
    CoinTransaction.objects.create(
        wallet=wallet, amount=-order.coins, reason=CoinTransaction.Reason.PAYMENT_REFUND, order=order,
    )
    order.status = PaymentOrder.Status.CANCELLED
    order.save(update_fields=["status"])
    return True
