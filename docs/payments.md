# Payments (Payme + Click)

Coins: **100 000 UZS = 10 coins** (10 000 UZS per coin). Applying to one project costs **10 coins**.
Every approved studio/freelancer gets **20 coins** (two projects) once, on approval.
All of this is configured in `poydevor/settings.py` (`COIN_PRICE_UZS`, `OFFER_COST_COINS`,
`SIGNUP_BONUS_COINS`, `COIN_PACKAGES`).

Both providers are **optional and off by default**. A provider switches on only when *all* its
environment variables are set; until then it is hidden on the Store tab and its callback URL answers
with a normal "not authorized" JSON response. Adding the keys later needs no migration and does not
touch any balance: coins are only ever added by a confirmed payment.

## Environment variables

| Variable | Provider | Where to find it |
|---|---|---|
| `PAYME_MERCHANT_ID` | Payme | Payme business cabinet → your cash register (Kassa) → ID |
| `PAYME_KEY` | Payme | Same page → the key (use the *test* key while testing) |
| `PAYME_TEST_MODE` | Payme | `True` while testing (sends customers to `test.paycom.uz`), unset/`False` for live |
| `CLICK_SERVICE_ID` | Click | Click merchant cabinet → your service |
| `CLICK_MERCHANT_ID` | Click | Click merchant cabinet |
| `CLICK_SECRET_KEY` | Click | Click merchant cabinet → service → secret key |

## Callback URLs to enter in the provider cabinets

| Provider | Field | URL |
|---|---|---|
| Payme | Endpoint URL | `https://<your-domain>/payments/payme/` |
| Click | Prepare URL | `https://<your-domain>/payments/click/prepare/` |
| Click | Complete URL | `https://<your-domain>/payments/click/complete/` |

Payme: in the cabinet, define **one account field named `order_id`** (type: numeric). The order id is
what Payme sends back to identify the payment.

## How it stays safe

* A payment is a `PaymentOrder`; coins are added by `wallet.services.credit_order`, which is
  idempotent (a provider retrying a callback never adds coins twice).
* A refund (Payme "cancel after payment") takes the coins back only if the wallet still holds them;
  otherwise Payme is told the payment cannot be cancelled.
* Webhooks always answer with valid JSON (never a 500), verify Payme's Basic auth / Click's MD5
  signature, and re-check the amount against the stored order.
