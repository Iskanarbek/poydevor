from django.contrib import admin

from wallet.models import ClickTransaction, CoinTransaction, PaymeTransaction, PaymentOrder, Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ["architect", "balance"]
    search_fields = ["architect__user__first_name", "architect__user__last_name", "architect__user__phone"]


@admin.register(CoinTransaction)
class CoinTransactionAdmin(admin.ModelAdmin):
    list_display = ["wallet", "amount", "reason", "order", "created_at"]
    list_filter = ["reason"]


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = ["id", "wallet", "provider", "coins", "amount_uzs", "status", "created_at", "paid_at"]
    list_filter = ["provider", "status"]


admin.site.register(PaymeTransaction)
admin.site.register(ClickTransaction)
