from django.contrib import admin

from wallet.models import CoinTransaction, Wallet

admin.site.register(Wallet)
admin.site.register(CoinTransaction)
