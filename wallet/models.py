from django.db import models

from architects.models import ArchitectProfile


class Wallet(models.Model):
    architect = models.OneToOneField(ArchitectProfile, on_delete=models.CASCADE, related_name="wallet")
    balance = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.architect} — {self.balance} tanga"


class PaymentOrder(models.Model):
    """One attempt to buy coins. Its id is what Payme (``account.order_id``)
    and Click (``merchant_trans_id``) send back to us, and the coins are only
    ever credited by ``wallet.services.credit_order``."""

    class Provider(models.TextChoices):
        PAYME = "payme", "Payme"
        CLICK = "click", "Click"

    class Status(models.TextChoices):
        CREATED = "created", "Kutilmoqda"
        PAID = "paid", "To'langan"
        CANCELLED = "cancelled", "Bekor qilingan"

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="payment_orders")
    provider = models.CharField(max_length=10, choices=Provider.choices)
    coins = models.PositiveIntegerField()
    amount_uzs = models.PositiveBigIntegerField(help_text="So'mda")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} {self.get_provider_display()} — {self.coins} tanga ({self.get_status_display()})"

    @property
    def amount_tiyin(self) -> int:
        return self.amount_uzs * 100


class CoinTransaction(models.Model):
    class Reason(models.TextChoices):
        TOPUP = "topup", "To'ldirish"
        OFFER_SPEND = "offer_spend", "Ariza uchun sarflandi"
        SIGNUP_BONUS = "signup_bonus", "Ro'yxatdan o'tish sovg'asi"
        PAYMENT_REFUND = "payment_refund", "To'lov qaytarildi"
        OFFER_REFUND = "offer_refund", "Ariza uchun tangalar qaytarildi"

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    amount = models.IntegerField()
    reason = models.CharField(max_length=20, choices=Reason.choices)
    order = models.ForeignKey(
        PaymentOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name="coin_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # A payment can add its coins once and take them back once, no
            # matter how many times a provider retries a callback.
            models.UniqueConstraint(
                fields=["order", "reason"],
                condition=models.Q(order__isnull=False),
                name="unique_coin_transaction_per_order_reason",
            ),
            # Every wallet gets its sign-up bonus at most once.
            models.UniqueConstraint(
                fields=["wallet"],
                condition=models.Q(reason="signup_bonus"),
                name="unique_signup_bonus_per_wallet",
            ),
        ]


class PaymeTransaction(models.Model):
    """Payme's view of a payment (Merchant API). Times are Unix milliseconds,
    as the protocol requires; ``state`` follows Payme's codes:
    1 created, 2 performed, -1 cancelled before, -2 cancelled after payment."""

    payme_id = models.CharField(max_length=64, unique=True)
    order = models.ForeignKey(PaymentOrder, on_delete=models.PROTECT, related_name="payme_transactions")
    amount = models.PositiveBigIntegerField(help_text="Tiyinda")
    state = models.SmallIntegerField()
    reason = models.SmallIntegerField(null=True, blank=True)
    payme_time = models.BigIntegerField()
    create_time = models.BigIntegerField()
    perform_time = models.BigIntegerField(default=0)
    cancel_time = models.BigIntegerField(default=0)

    def __str__(self):
        return f"Payme {self.payme_id} (state {self.state})"


class ClickTransaction(models.Model):
    """Click's view of a payment (Shop API prepare/complete)."""

    class Status(models.TextChoices):
        PREPARED = "prepared", "Tayyorlandi"
        COMPLETED = "completed", "Yakunlandi"
        CANCELLED = "cancelled", "Bekor qilindi"

    click_trans_id = models.BigIntegerField(unique=True)
    click_paydoc_id = models.BigIntegerField(null=True, blank=True)
    order = models.ForeignKey(PaymentOrder, on_delete=models.PROTECT, related_name="click_transactions")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PREPARED)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Click {self.click_trans_id} ({self.get_status_display()})"
