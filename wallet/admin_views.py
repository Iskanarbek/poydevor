"""The revenue dashboard: a staff-only page (not Django admin's own UI, but
styled like the rest of the site) answering "how much money came in" — today,
this week, this month, this year, and all time, plus a day-by-day and
month-by-month breakdown."""
from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.shortcuts import render
from django.utils import timezone

from poydevor.staff_panel import staff_required
from wallet.models import PaymentOrder

Status = PaymentOrder.Status


def _totals(queryset):
    agg = queryset.aggregate(revenue=Sum("amount_uzs"), orders=Count("id"), coins=Sum("coins"))
    return {
        "revenue": agg["revenue"] or 0,
        "orders": agg["orders"] or 0,
        "coins": agg["coins"] or 0,
    }


@staff_required
def revenue_dashboard(request):
    paid = PaymentOrder.objects.filter(status=Status.PAID)

    today = timezone.localdate()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)

    summary = {
        "today": _totals(paid.filter(paid_at__date__gte=today)),
        "week": _totals(paid.filter(paid_at__date__gte=start_of_week)),
        "month": _totals(paid.filter(paid_at__date__gte=start_of_month)),
        "year": _totals(paid.filter(paid_at__date__gte=start_of_year)),
        "all_time": _totals(paid),
    }

    daily = list(
        paid.filter(paid_at__date__gte=today - timedelta(days=13))
        .annotate(day=TruncDate("paid_at"))
        .values("day")
        .annotate(revenue=Sum("amount_uzs"), orders=Count("id"))
        .order_by("-day")
    )

    twelve_months_ago = (start_of_year.replace(year=start_of_year.year - 1))
    monthly = list(
        paid.filter(paid_at__date__gte=twelve_months_ago)
        .annotate(month=TruncMonth("paid_at"))
        .values("month")
        .annotate(revenue=Sum("amount_uzs"), orders=Count("id"))
        .order_by("-month")
    )

    recent = list(
        paid.select_related("wallet__architect__user")
        .order_by("-paid_at")[:25]
    )

    return render(request, "admin/wallet/revenue_dashboard.html", {
        "summary": summary, "daily": daily, "monthly": monthly, "recent": recent,
    })
