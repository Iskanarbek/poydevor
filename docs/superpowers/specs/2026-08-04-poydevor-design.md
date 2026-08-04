# Poydevor — Design Spec

Date: 2026-08-04

## Summary

Poydevor is a Django web platform (similar to buildmost) connecting people who
want a house designed/built ("foydalanuvchi" / user) with architects. The
entire UI is in Uzbek. Users can either post a project brief for architects to
respond to, or browse and directly apply to a chosen architect. Architects
build a portfolio, browse open project postings, and spend coins to get
involved in a project (max 3 architects per posting).

## Stack

- Django 5, SQLite (dev; swappable to Postgres later)
- Tailwind CSS for styling, Alpine.js for client-side interactivity
  (auto-rotating image carousels, style filters, dynamic form toggles)
- No separate frontend build/deploy — server-rendered templates
- Local filesystem storage under `/media` for uploads (plan PDFs, portfolio
  images, profile photos)

## Apps

- `accounts` — custom `User` model, phone-based auth
- `architects` — architect profile, portfolio projects/images, skills, style
  tags, reviews
- `applications` — user project postings ("elon joylashtirish")
- `offers` — links an architect to an application (send/accept/reject,
  contact reveal, max 3 architects per application)
- `wallet` — architect coin balance, transaction log, mock top-up

## Data model

### accounts.User (custom user model)

- `phone` (unique, `USERNAME_FIELD`), `password`
- `first_name`, `last_name`
- `role`: `user` | `architect`

### architects.ArchitectProfile (OneToOne → User)

- `bio` (text)
- `telegram_username`
- `rating` (decimal, computed average of Review ratings; 0 if no reviews)
- `completed_projects_count` (int, incremented when an offer's project is
  marked complete)
- `styles` (M2M → Style lookup table: modern, classic, minimalism, etc.)
- `skills` (short text list / M2M to a Skill lookup table)
- `avatar` (optional image; placeholder shown in UI if absent)

### architects.PortfolioProject (FK → ArchitectProfile)

- `title`, `description`, `style` (FK → Style)
- ordering field for carousel order

### architects.PortfolioImage (FK → PortfolioProject)

- `image`, `order`

### architects.Review (FK → ArchitectProfile, FK → User, FK → Offer)

- `rating` (1–5), `comment`, `created_at`
- one review per completed offer

### applications.Application (FK → User as owner)

- `size_m2` (nullable — null when "I don't know, calculate roughly" is
  chosen)
- `size_unknown` (bool)
- `rooms_count`
- `location`
- `interior_style` (FK → Style, optional)
- `budget` (optional, decimal)
- `plan_pdf` (optional file)
- `status`: `open` | `in_progress` | `closed`
- `created_at`

### offers.Offer (FK → Application, FK → ArchitectProfile)

- `status`: `pending` | `accepted` | `rejected`
- `source`: `architect_applied` (architect spent coins on an open posting) |
  `user_invited` (user sent application directly from an architect's profile)
- `created_at`, `decided_at`
- Constraint enforced in service layer: an Application may have at most 3
  Offers with status in (`pending`, `accepted`) at once.

### wallet.Wallet (OneToOne → ArchitectProfile)

- `balance` (int, coins)

### wallet.CoinTransaction (FK → Wallet)

- `amount` (+/-), `reason`: `topup` | `offer_spend`
- `created_at`

## Core flows

### Auth

- Signup: name, surname, phone, password, role checkbox (user/architect).
  Phone must be unique. Architect role continues into a required minimal
  portfolio step (bio + at least one skill) before reaching their dashboard;
  portfolio projects/images can be added afterward.
- Login: phone + password (no OTP).

### User: post a project ("elon joylashtirish")

Form fields: m² size OR "I don't know — estimate roughly" toggle (switches
input to rooms-based rough sizing), rooms count, location, interior style
(optional), budget (optional), house plan PDF (optional). Posting creates an
open `Application` visible to architects in their "open applications" tab.

### User: browse architects

Grid of architect cards: auto-rotating portfolio photo carousel (left-to-right
scroll/rotate), name, rating, completed-projects count; placeholder graphic
if no photo. A style filter narrows both the card grid and, once inside a
profile, which portfolio projects/images are shown (filtered items never
appear, even while scrolling).

Architect profile page: avatar (placeholder if absent), name, rating, project
count, skills, full portfolio (all projects with images), bio. "Send
application" button opens the project-details form (same fields as posting a
project) if the user hasn't already got an open application, otherwise lets
them pick an existing one. Before sending, show a notice: contact details
become visible only after the architect accepts. This creates an `Offer`
with `source=user_invited`.

### Offer response (architect)

Architect accepts or rejects a pending offer.
- Rejected → user sees a rejection message + prompt to choose another
  architect.
- Accepted → user sees an acceptance message and the architect's phone +
  telegram become visible. If the offer's application already had other
  pending offers from the same source flow, those remain independently
  decidable (a user can still be waiting on a second architect).

### User: choosing among up to 3 architect replies

When an open `Application` receives offers from architects browsing postings
(`source=architect_applied`), the user sees up to 3 architect cards attached
to their posting. They can review each and accept one (revealing contacts) or
reject any/all.

### Architect panel — 3 tabs

1. **Portfolio** — edit profile (bio, skills, telegram, styles, avatar),
   manage portfolio projects and images (add/edit/delete, reorder for
   carousel).
2. **Applications** (sent & received) — offers the architect sent
   (`architect_applied`) and offers users sent them (`user_invited`), with
   status.
3. **Open postings** — browse all open user `Application`s with
   size/rooms/budget/location/style filters. "Get involved" spends 20 coins
   (blocked if balance < 20 or the posting already has 3 active offers),
   creating a `pending` Offer.

Plus a **Wallet** page: balance, transaction history, "Buy coins" button with
packages (e.g. 20 / 40 / 100 coins ≈ $5 / $10 / $25) — instant mock credit
(no real payment gateway yet), logged as a `CoinTransaction`.

### Reviews

Once an accepted offer's project is marked complete (a "Loyihani yakunlash"
action available to the user on an accepted offer), the user can leave a
1–5 star rating + comment. This creates a `Review` and updates the
architect's `rating` (recomputed average) and `completed_projects_count`.

### Seed data

A management command/fixture creates one demo architect account preloaded
with 1000 coins, for testing the coin-spend flow without needing many
top-ups.

## Out of scope for v1

- Real SMS OTP verification (phone uniqueness only, no verification code)
- Real payment gateway integration for coins (mock instant credit)
- Cloud file storage (local `/media` only)
- Messaging/chat between user and architect beyond the offer accept/reject +
  revealed telegram/phone (no in-app chat)
