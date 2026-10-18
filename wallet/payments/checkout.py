"""Build the URL that sends a customer to Payme's or Click's payment page."""
import base64
from urllib.parse import urlencode

from wallet.models import PaymentOrder
from wallet.payments.config import click_config, payme_config


def payme_checkout_url(order: PaymentOrder, return_url: str) -> str:
    config = payme_config()
    params = (
        f"m={config['MERCHANT_ID']};ac.order_id={order.pk};a={order.amount_tiyin};"
        f"l=uz;c={return_url}"
    )
    encoded = base64.b64encode(params.encode()).decode()
    host = "https://test.paycom.uz" if config.get("TEST_MODE") else "https://checkout.paycom.uz"
    return f"{host}/{encoded}"


def click_checkout_url(order: PaymentOrder, return_url: str) -> str:
    config = click_config()
    query = urlencode({
        "service_id": config["SERVICE_ID"],
        "merchant_id": config["MERCHANT_ID"],
        "amount": order.amount_uzs,
        "transaction_param": order.pk,
        "return_url": return_url,
    })
    return f"https://my.click.uz/services/pay?{query}"


def checkout_url(order: PaymentOrder, return_url: str) -> str:
    if order.provider == PaymentOrder.Provider.PAYME:
        return payme_checkout_url(order, return_url)
    return click_checkout_url(order, return_url)
