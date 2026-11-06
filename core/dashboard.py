"""Numbers for the admin panel's home page and sidebar (django-unfold callbacks)."""

import datetime as dt
import json

from django.db.models import Count, Q, Sum
from django.urls import reverse

from core import services
from core.models import Employee, Order, Product, Team, WorkEntry
from core.reports import money

CHART_DAYS = 14


def pending_badge(request):
    """Shown next to "Ish yozuvlari" in the sidebar: entries still waiting for a manager."""
    count = WorkEntry.objects.filter(status=WorkEntry.Status.PENDING).count()
    # An empty string hides the badge; None was shown as the word "NONE".
    return count or ""


def open_orders_badge(request):
    """Shown next to "Zakazlar": orders still being sewn."""
    return Order.objects.filter(status__in=Order.OPEN_STATUSES).count() or ""


def _fmt(number):
    return f"{number:,}".replace(",", " ")


def dashboard_callback(request, context):
    day = services.today()
    entries_today = list(WorkEntry.objects.filter(date=day).exclude(status=WorkEntry.Status.REJECTED))
    approved_today = [e for e in entries_today if e.status == WorkEntry.Status.APPROVED]
    workers = Employee.objects.filter(role=Employee.Role.WORKER, is_active=True)
    worker_count = workers.count()
    entered = len({e.worker_id for e in entries_today})
    pending_count = WorkEntry.objects.filter(status=WorkEntry.Status.PENDING).count()

    entries_url = reverse("admin:core_workentry_changelist")
    kpis = [
        {
            "title": "Bugun tasdiqlangan",
            "value": f"{_fmt(sum(e.quantity for e in approved_today))} dona",
            "note": f"Kutilmoqda: {_fmt(sum(e.quantity for e in entries_today) - sum(e.quantity for e in approved_today))} dona",
            "icon": "inventory_2",
        },
        {
            "title": "Bugungi ish haqi",
            "value": money(sum(e.amount for e in approved_today)),
            "note": "Faqat tasdiqlangan ishlar bo'yicha",
            "icon": "payments",
        },
        {
            "title": "Ish kiritgan ishchilar",
            "value": f"{entered} / {worker_count}",
            "note": f"{max(worker_count - entered, 0)} kishi hali kiritmagan",
            "icon": "groups",
            "progress": round(entered * 100 / worker_count) if worker_count else 0,
        },
        {
            "title": "Tasdiq kutayotgan",
            "value": f"{pending_count} ta yozuv",
            "note": "Ko'rish uchun bosing",
            "icon": "pending_actions",
            "href": f"{entries_url}?status__exact={WorkEntry.Status.PENDING}",
        },
    ]

    # Approved pieces per day for the last two weeks.
    start = day - dt.timedelta(days=CHART_DAYS - 1)
    per_day = dict(
        WorkEntry.objects.filter(date__gte=start, date__lte=day, status=WorkEntry.Status.APPROVED)
        .values_list("date")
        .annotate(total=Sum("quantity"))
    )
    days = [start + dt.timedelta(days=i) for i in range(CHART_DAYS)]
    chart = {
        "labels": [d.strftime("%d.%m") for d in days],
        "datasets": [
            {
                "label": "Tasdiqlangan dona",
                "data": [per_day.get(d, 0) for d in days],
                "backgroundColor": "var(--color-primary-600)",
                "borderRadius": 6,
                "maxBarThickness": 28,
                "barPercentage": 0.7,
            }
        ],
    }
    week = sum(per_day.get(d, 0) for d in days[-7:])
    prev_week = sum(per_day.get(d, 0) for d in days[:7])

    # Each team today.
    teams = (
        Team.objects.select_related("manager")
        .annotate(
            members_active=Count(
                "members",
                filter=Q(members__is_active=True, members__role=Employee.Role.WORKER),
                distinct=True,
            ),
        )
        .order_by("name")
    )
    team_rows = []
    for t in teams:
        qs = WorkEntry.objects.filter(date=day, worker__team=t)
        totals = qs.aggregate(
            approved=Sum("quantity", filter=Q(status=WorkEntry.Status.APPROVED)),
            pending=Sum("quantity", filter=Q(status=WorkEntry.Status.PENDING)),
            workers=Count("worker", distinct=True, filter=~Q(status=WorkEntry.Status.REJECTED)),
        )
        team_rows.append(
            [
                t.name,
                t.manager.full_name if t.manager else "-",
                f"{totals['workers'] or 0} / {t.members_active}",
                _fmt(totals["approved"] or 0),
                _fmt(totals["pending"] or 0),
            ]
        )

    latest_pending = list(
        WorkEntry.objects.filter(status=WorkEntry.Status.PENDING)
        .select_related("worker", "operation__product")
        .order_by("-date", "-pk")[:6]
    )

    context.update(
        {
            "today": day,
            "kpis": kpis,
            "chart": json.dumps(chart),
            "week_total": _fmt(week),
            "week_change": round((week - prev_week) * 100 / prev_week) if prev_week else None,
            "team_table": {
                "headers": ["Guruh", "Sardor", "Kiritganlar", "Tasdiqlangan", "Kutilmoqda"],
                "rows": team_rows,
            },
            "latest_pending": latest_pending,
            "entries_url": entries_url,
            "product_count": Product.objects.filter(is_active=True).count(),
        }
    )
    return context
