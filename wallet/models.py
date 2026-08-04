from django.db import models

from architects.models import ArchitectProfile


class Wallet(models.Model):
    architect = models.OneToOneField(ArchitectProfile, on_delete=models.CASCADE, related_name="wallet")
    balance = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.architect} — {self.balance} tanga"


class CoinTransaction(models.Model):
    class Reason(models.TextChoices):
        TOPUP = "topup", "To'ldirish"
        OFFER_SPEND = "offer_spend", "Ariza uchun sarflandi"

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    amount = models.IntegerField()
    reason = models.CharField(max_length=20, choices=Reason.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
