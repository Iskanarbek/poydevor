from django.urls import path

from wallet import views

app_name = "wallet"
urlpatterns = [
    path("panel/hamyon/", views.dashboard, name="dashboard"),
    path("panel/hamyon/sotib-olish/", views.buy_coins, name="buy"),
]
