from django.db import transaction

from wallet.models import CoinTransaction, Wallet


class InsufficientCoinsError(Exception):
    pass


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
