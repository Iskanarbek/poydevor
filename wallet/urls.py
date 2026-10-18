from django.urls import path

from wallet import views

app_name = "wallet"
urlpatterns = [
    path("panel/hamyon/", views.dashboard, name="dashboard"),
    path("panel/hamyon/sotib-olish/", views.buy_coins, name="buy"),
    # Callbacks from the payment providers
    path("payments/payme/", views.payme_webhook, name="payme_webhook"),
    path("payments/click/prepare/", views.click_prepare, name="click_prepare"),
    path("payments/click/complete/", views.click_complete, name="click_complete"),
]
