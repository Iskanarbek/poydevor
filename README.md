# Poydevor

A Django marketplace connecting clients ("mijoz") who need an interior/architecture
project done with architects, studios, and studio employees in Uzbekistan. Clients
post orders; architects and studios spend in-app coins to apply; studios assign
accepted orders to their own employees; payments for coins go through Payme/Click.

This README is written for someone who has **never seen this project before** and
needs to get it running locally and deployed, including the payment system.

---

## 1. What's in this project

| App | What it does |
|---|---|
| `accounts` | Custom user model (login by phone number, no username), auth backends, the staff admin panel login |
| `architects` | Architect/studio/employee registration, approval, portfolio, admin-panel staff views |
| `applications` | Client orders ("e'lon") |
| `offers` | An architect/studio applying to an order, accepting it, and (for studios) assigning the accepted work to an employee |
| `wallet` | Coins, Payme/Click payment integration, the revenue dashboard |
| `reviews` | Client reviews of completed work |

Staff panel (our own, not Django's default admin skin): `/admin-panel/`
Django's built-in admin (for deep data fixes): `/admin/`

---

## 2. Requirements

- Python 3.12 or newer (the project refuses to start on anything older than Django
  5.2 supports)
- pip
- No database server required to get started — SQLite works out of the box.
  Postgres is supported too (see env vars below) but optional.

---

## 3. Local setup (from a zip, no GitHub needed)

```bash
# 1. Unzip the project and cd into it
cd poydevor

# 2. Create a virtual environment and install dependencies
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 3. Apply database migrations
venv/bin/python manage.py migrate

# 4. Create your own admin account (you'll use this to log into /admin-panel/)
venv/bin/python manage.py createsuperuser
# It will ask for: phone (e.g. +998901234567), first name, last name, role
# (type "user"), then a password. is_staff/is_superuser are set automatically
# by createsuperuser.

# 5. Run it
venv/bin/python manage.py runserver 8080
```

Open **http://localhost:8080**. Log into the staff panel at
**http://localhost:8080/admin-panel/kirish/** with the phone + password you just set.

By default `DEBUG` is **off** (see below) — for local development, set
`DJANGO_DEBUG=true` before running `runserver`, or use the included
`dev_server.py` helper, which reads a local `local_env.sh` file:

```bash
# Create local_env.sh (never commit this — see .gitignore) with:
export DJANGO_DEBUG="true"
export DJANGO_SECRET_KEY="any-random-string-for-local-dev"
# ... plus Payme/Click vars if you want payments working locally too (section 6)

venv/bin/python dev_server.py   # same as runserver 8080, but loads local_env.sh first
```

---

## 4. Running the tests

```bash
venv/bin/python manage.py test
```

Nearly 300 tests cover registration, approvals, portfolios, orders, offers,
studio/employee assignment, wallet/payments, and the staff panel. Run this
after any change — it's fast (well under a minute) and catches real regressions.

---

## 5. Environment variables — the full list

Nothing in this project is hardcoded to Vercel, GitHub, or any specific host.
Every setting below comes from the environment, so it runs identically on a
VPS, a shared-hosting "Python app" panel (Timeweb, Beget, cPanel, etc.), or
anywhere else that can run `pip install` and a WSGI app.

| Variable | Required? | What it is |
|---|---|---|
| `DJANGO_SECRET_KEY` | **Yes, in production** | A random string Django uses to sign sessions/cookies. Generate one: `venv/bin/python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` |
| `DJANGO_DEBUG` | No (defaults to `False`, correct for production) | Set to `true` only for local development. **Never leave this on in production** — it exposes source code and settings in error pages. |
| `DJANGO_ALLOWED_HOSTS` | **Yes, in production** | Your real domain(s), comma-separated, e.g. `poydevor.uz,www.poydevor.uz` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | **Yes, if served over HTTPS** | Same domains with scheme, e.g. `https://poydevor.uz,https://www.poydevor.uz` |
| `DJANGO_HTTPS` | Recommended, once HTTPS is working | `true` makes cookies HTTPS-only and forces every request to HTTPS. Leave unset until you've confirmed HTTPS actually works end to end — turning it on too early can lock everyone out of login (an HTTPS-only cookie is simply dropped over plain HTTP). |
| `DATABASE_URL` | No (falls back to SQLite) | A Postgres connection string, if your host offers Postgres. SQLite is fine on a host with a persistent disk (any ordinary server — just not Vercel's serverless runtime). |
| `PAYME_MERCHANT_ID` | No — payments stay off without it | Payme business cabinet → your cash register ("kassa") → ID |
| `PAYME_KEY` | No — must be set together with the above | The matching key: **test key** while `PAYME_TEST_MODE=true`, **production key** otherwise. These are two different values in your Payme cabinet — don't mix them up. |
| `PAYME_TEST_MODE` | No (defaults off = production) | `true` sends customers to Payme's sandbox (`test.paycom.uz`, no real money). Leave unset for real payments. |
| `CLICK_SERVICE_ID` / `CLICK_MERCHANT_ID` / `CLICK_SECRET_KEY` | No | Click merchant cabinet. All three needed together to turn Click on. |
| `CRON_SECRET` | No | Only if you wire up `/internal/expire-orders/` to a daily cron job (deletes orders nobody confirmed are still open, refunds the architects who applied). |
| `BLOB_READ_WRITE_TOKEN` | No — **leave unset on a normal server** | Vercel-only: redirects uploads to Vercel Blob storage because Vercel's own filesystem can't be written to. On a real server (VPS, shared hosting) you want this **unset** — uploads then just save to local disk, which is correct and simpler. |

A provider (Payme or Click) is **off** unless every one of its variables is set.
Nothing crashes if they're missing — the "buy coins" page just hides that
option, and its webhook answers with a proper "not authorized" response. You
can add real credentials later with zero code changes and zero downtime.

---

## 6. The payment system (Payme + Click)

### How coins work

- **1 coin = 10,000 so'm.** (`COIN_PRICE_UZS` in `poydevor/settings.py`)
- **Applying to one project costs 10 coins = 100,000 so'm** (`OFFER_COST_COINS`).
  This is what an individual architect or a studio spends each time they apply
  to a client's order. Being invited by a client directly costs nothing.
- Every newly approved architect/studio gets **20 coins free** (two project
  applications) the moment they're approved — a one-time signup bonus.
- Coin packages for sale: 10 / 20 / 50 / 100 coins — 100,000 / 200,000 /
  500,000 / 1,000,000 so'm respectively.
- **Currency: Uzbek so'm (UZS) only.** Payme and Click are Uzbekistan-only
  payment systems; there is no dollar option, and none is needed — all
  pricing, invoicing, and payouts are in so'm.
- **Cards accepted: Uzcard, Humo, and Visa** all work through Payme's own
  checkout page (this is Payme's own card support, not something this app
  controls or restricts). You don't need a separate integration per card type.

### Setting it up

1. Get your credentials from your Payme business cabinet (business.payme.uz):
   the merchant ID, and **two separate keys** — a test key and a production
   key. (Click works the same way via its own merchant cabinet, with 3 values.)
2. Set the environment variables from the table above, wherever you deploy
   (or in `local_env.sh` for local testing).
3. In the Payme/Click cabinet, register these callback URLs (swap in your
   real domain):

   | Provider | Field | URL |
   |---|---|---|
   | Payme | Endpoint URL | `https://your-domain/payments/payme/` |
   | Click | Prepare URL | `https://your-domain/payments/click/prepare/` |
   | Click | Complete URL | `https://your-domain/payments/click/complete/` |

   Payme also needs **one account field named `order_id`** (type: numeric)
   defined in the cabinet — that's how Payme tells us which payment it's
   talking about.

4. Start with `PAYME_TEST_MODE=true` and the **test** key. Verify it (see
   below), then switch to the **production** key and remove
   `PAYME_TEST_MODE` (or set it to `false`) to go live. Same merchant ID
   either way — only the key and the mode flag change.

### How it was verified (this exact setup)

Payme's sandbox (`test.paycom.uz`) is a developer console, not a customer
checkout form — it drives *your* webhook by calling it with the same
JSON-RPC protocol Payme's real production servers use. Both need a webhook
URL they can reach, so on a laptop behind `localhost` the realistic way to
prove the integration works is to call the webhook exactly as Payme does.
That's what was done here: `CheckPerformTransaction` → `CreateTransaction` →
`PerformTransaction` was sent straight to `/payments/payme/` with real test
credentials. Result: the order moved from `created` to `paid`, the wallet's
balance increased by exactly the coins bought, and retrying the same call
(which Payme does for real, to confirm delivery) did **not** double-credit
anything. Wrong credentials were correctly rejected. This is the same code
path a real browser checkout exercises — once the webhook URL above is
registered against a real public domain, production payments go through the
same, already-verified logic.

### How it stays safe

- Coins are only ever added by `wallet.services.credit_order`, which is
  idempotent — a provider retrying its callback (which both providers do)
  never adds coins twice.
- A refund (Payme cancelling a transaction after payment) takes the coins
  back only if the wallet still holds them; otherwise Payme is told it can't
  be cancelled (so you can't end up with a negative balance).
- Webhooks always answer with a valid response, never a crash page; they
  verify Payme's Basic-auth key / Click's MD5 signature and re-check the
  amount against the stored order before doing anything.

More detail: [`docs/payments.md`](docs/payments.md).

---

## 7. Deploying to a real server (no GitHub, zip upload is fine)

This works on any host that can run Python — a VPS, or shared hosting with a
"Python app" panel (Timeweb, Beget, cPanel's "Setup Python App", etc.).

### Step 1 — Package the code correctly

Don't zip the raw project folder — it would drag in `venv/` (huge,
machine-specific), `db.sqlite3` (your local test data), and `local_env.sh`
(your local secrets). From a terminal in the project:

```bash
git archive -o poydevor.zip HEAD
```

(No git repo? Just manually zip the project folder but **exclude** `venv/`,
`db.sqlite3`, `local_env.sh`, `__pycache__/`, and `staticfiles/`.)

Upload and extract that zip on the server.

### Step 2 — Install and configure

```bash
pip install -r requirements.txt
```

Set every environment variable from section 5 that applies to you, using
whatever mechanism your host provides (most "Python app" panels have a
dedicated environment-variables section in their UI).

### Step 3 — Migrate, collect static files, create an admin

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

`collectstatic` is required — without it, pages still work but look
unstyled (no CSS), because static files are served by WhiteNoise once
`DEBUG=False`, and WhiteNoise serves from the `collectstatic` output.

### Step 4 — Point the host at the app

Whatever your host's panel asks for as the WSGI entry point:

```
poydevor.wsgi:application
```

### Step 5 — Go live with payments

Once the app is reachable at a real HTTPS domain, register the webhook URLs
from section 6 in your Payme/Click cabinets, switch `PAYME_KEY` to the
production value, and you're done — no code changes needed.

---

## 8. Uploads and safety

The site accepts **only PDF and JPG** for the two document uploads: a portfolio project's
file and a client's house file. Both open on any phone or computer with no extra app, and
neither can run a program. Everything else (Word, DWG, ZIP, PNG, video, programs, ...) is
refused with a message telling the person to upload a PDF or JPG.

Portfolio *photos* are a separate box: they are pictures shown on the site, and the browser
converts them to JPG before sending when it can.

A file is accepted only if all of this is true (`poydevor/upload_safety.py`, one small file):

- the name ends in `.pdf`, `.jpg` or `.jpeg`
- the content really is that kind of file, so a program, web page, ZIP or APK renamed to
  `.pdf` or `.jpg` is refused (the first bytes give it away)
- a JPG opens as a real picture
- a PDF has no JavaScript, auto-launch or hidden embedded files
- the name has no hidden right-to-left characters that fake an extension

Limits: 50 MB for a project file, 20 MB for a client's house file.

**Second layer: how files are served.** Everything under `/media/` is sent with
`X-Content-Type-Options: nosniff`, and anything that is not a photo, PDF or video is forced to
download instead of opening. `runserver` does this through `poydevor/middleware.py`. On a real
server nginx serves `/media/` itself, so put the same rules in the nginx site config (replace
the plain `location /media/` block):

```nginx
# Photos, PDFs and videos open in the browser; every other file type downloads.
map $uri $media_disposition {
    default                                   "attachment";
    ~*\.(jpe?g|png|gif|webp|avif|pdf|mp4|webm|mov)$  "";
}

location /media/ {
    alias /srv/poydevor/media/;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Content-Disposition $media_disposition always;
    add_header Content-Security-Policy "sandbox; default-src 'none'" always;
}
```

This is a strong first defence, not antivirus. If you later want more file types, edit
`ALLOWED_EXTENSIONS` and add a matching content check in `upload_safety.py`; do not simply
remove the check. For real malware scanning of every upload, install **ClamAV**
(`apt install clamav-daemon`) and scan new files from a small Django hook.

---

## 9. The staff admin panel

Two separate places to manage the platform:

- **`/admin-panel/`** — our own panel, styled like the rest of the site.
  Log in with phone + password (`createsuperuser`, or anyone you later give
  `is_staff=True`). From here you can:
  - Search architects/studios by name or phone
  - Review and verify/reject a finished portfolio (what unlocks an architect
    to actually apply to orders)
  - Approve/reject a pending registration
  - Freeze/unfreeze an account (with a reason) — a frozen account can't log
    in at all, but nothing about it is deleted
  - See revenue: today / this week / this month / this year / all-time,
    plus a day-by-day and month-by-month breakdown
- **`/admin/`** — Django's own built-in admin, kept for lower-level/bulk
  data edits the custom panel doesn't cover.

Note: staff accounts can **only** log in through `/admin-panel/kirish/`
(phone + password). The ordinary site login (`/kirish/`) is deliberately
phone-only with no password, for clients and architects — letting a staff
account through that door would mean anyone who knew their phone number
could sign in as them.

---

## 10. Project structure quick reference

```
accounts/     custom User model, phone-based login, staff panel login
architects/   registration, approval, portfolio, staff panel views
applications/ client orders
offers/       applying/accepting orders, studio→employee assignment
wallet/       coins, Payme/Click, revenue dashboard
reviews/      client reviews
poydevor/     project settings, root URLs, cross-cutting views, staff_panel.py
templates/    all HTML, including templates/staff_panel/ and templates/admin/
docs/         payments.md has more payment detail; superpowers/ has the
              original design spec and implementation plan
```
