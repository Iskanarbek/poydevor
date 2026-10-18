import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from architects.navigation import dashboard_url
from wallet.models import PaymentOrder
from wallet.payments import click, payme
from wallet.payments.checkout import checkout_url
from wallet.payments.config import is_enabled
from wallet.services import coin_price_uzs

logger = logging.getLogger(__name__)


def _architect_with_wallet(user):
    profile = getattr(user, "architect_profile", None)
    if profile is None or not hasattr(profile, "wallet"):
        raise Http404
    return profile


@login_required
def dashboard(request):
    """The wallet lives in the "Store" tab of the architect's dashboard."""
    profile = _architect_with_wallet(request.user)
    return redirect(dashboard_url(profile, "store"))


@login_required
@require_POST
def buy_coins(request):
    """Start paying for a coin package: create an order and hand the customer
    over to Payme or Click. If the chosen provider isn't set up (yet), tell
    the customer instead of failing."""
    profile = _architect_with_wallet(request.user)
    store_url = dashboard_url(profile, "store")

    try:
        coins = int(request.POST.get("coins", ""))
    except ValueError:
        coins = 0
    provider = request.POST.get("provider", "")

    if coins not in settings.COIN_PACKAGES:
        messages.error(request, "Noto'g'ri paket tanlandi.")
        return redirect(store_url)
    if provider not in PaymentOrder.Provider.values or not is_enabled(provider):
        messages.warning(request, "Bu to'lov usuli hozircha mavjud emas.")
        return redirect(store_url)

    order = PaymentOrder.objects.create(
        wallet=profile.wallet, provider=provider, coins=coins, amount_uzs=coin_price_uzs(coins),
    )
    return_url = request.build_absolute_uri(store_url)
    return redirect(checkout_url(order, return_url))


@csrf_exempt
def payme_webhook(request):
    return JsonResponse(payme.handle(request), json_dumps_params={"ensure_ascii": False})


@csrf_exempt
@require_POST
def click_prepare(request):
    return JsonResponse(click.prepare(request.POST))


@csrf_exempt
@require_POST
def click_complete(request):
    return JsonResponse(click.complete(request.POST))
