from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from wallet.models import Wallet
from wallet.services import topup_coins

PACKAGES = {"20": 20, "40": 40, "100": 100}


@login_required
def dashboard(request):
    wallet = get_object_or_404(Wallet, architect__user=request.user)
    return render(request, "wallet/dashboard.html", {"wallet": wallet, "packages": PACKAGES})


@login_required
def buy_coins(request):
    wallet = get_object_or_404(Wallet, architect__user=request.user)
    if request.method == "POST":
        amount = PACKAGES.get(request.POST.get("package"))
        if amount:
            topup_coins(wallet, amount)
    return redirect("wallet:dashboard")
