"""Business rules shared by the bot and the website.

Every function here is synchronous; the bot calls them through sync_to_async.
ServiceError messages are shown to the user as is (in Latin script; the bot
transliterates them when the user picked Cyrillic).
"""

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import Employee, EntryEdit, Operation, Product, Team, WorkEntry


class ServiceError(Exception):
    pass


def normalize_phone(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    return digits


def local_now():
    return timezone.localtime()


def today():
    return local_now().date()


def day_is_open(day, now=None):
    """Entries for a day can be created or edited only on that day, before closing time."""
    now = now or local_now()
    return day == now.date() and now.hour < settings.DAY_CLOSE_HOUR


def _require_open(day, now):
    if not day_is_open(day, now):
        raise ServiceError(
            f"Kun yopilgan: yozuvlarni faqat shu kuni soat {settings.DAY_CLOSE_HOUR}:00 gacha "
            "kiritish yoki o'zgartirish mumkin."
        )


def _validate_quantity(quantity):
    if not isinstance(quantity, int) or quantity < 1:
        raise ServiceError("Son musbat butun son bo'lishi kerak.")
    if quantity > settings.MAX_QUANTITY:
        raise ServiceError(f"Son juda katta (eng ko'pi {settings.MAX_QUANTITY}).")


# --- Registration -----------------------------------------------------------


def register_by_contact(telegram_id, phone, full_name):
    """Link a Telegram account to an employee by phone number.

    Returns (employee, is_new). An unknown phone creates an inactive worker
    that the boss activates in the admin panel.
    """
    phone = normalize_phone(phone)
    employee = Employee.objects.filter(phone=phone).first()
    if employee:
        if employee.telegram_id and employee.telegram_id != telegram_id:
            raise ServiceError("Bu raqam boshqa Telegram hisobiga bog'langan. Boshliqqa murojaat qiling.")
        Employee.objects.filter(telegram_id=telegram_id).exclude(pk=employee.pk).update(telegram_id=None)
        employee.telegram_id = telegram_id
        employee.save(update_fields=["telegram_id"])
        return employee, False
    Employee.objects.filter(telegram_id=telegram_id).update(telegram_id=None)
    employee = Employee.objects.create(
        full_name=full_name or phone,
        phone=phone,
        telegram_id=telegram_id,
        role=Employee.Role.WORKER,
        is_active=False,
    )
    return employee, True


def get_by_telegram(telegram_id):
    return (
        Employee.objects.select_related("team", "worker_type", "team__manager")
        .filter(telegram_id=telegram_id)
        .first()
    )


def set_script(employee, script):
    employee.script = script
    employee.save(update_fields=["script"])


def bosses():
    return list(
        Employee.objects.filter(role=Employee.Role.BOSS, is_active=True, telegram_id__isnull=False)
    )


@transaction.atomic
def set_site_password(employee, password):
    """Give a manager a login for the website: the username is the phone number."""
    from django.contrib.auth import get_user_model

    if not employee.is_manager:
        raise ServiceError("Sayt hisobi faqat boshqaruvchilar uchun.")
    if len(password or "") < 6:
        raise ServiceError("Parol kamida 6 belgi bo'lishi kerak.")
    user = employee.user
    if user is None:
        User = get_user_model()
        if User.objects.filter(username=employee.phone).exists():
            raise ServiceError("Bu telefon raqami bilan sayt hisobi allaqachon bor.")
        user = User(username=employee.phone)
    user.set_password(password)
    user.is_active = True
    user.save()
    if employee.user_id != user.pk:
        employee.user = user
        employee.save(update_fields=["user"])
    return user


def site_employee(user):
    """The active manager or boss behind a website login, or None."""
    if not user.is_authenticated:
        return None
    employee = Employee.objects.filter(user=user, is_active=True).select_related("team").first()
    if employee and (employee.is_manager or employee.is_boss):
        return employee
    return None


# --- Permissions ------------------------------------------------------------


def can_manage(manager, worker):
    if not manager.is_active:
        return False
    if manager.is_boss:
        return True
    return manager.is_manager and worker.team_id is not None and worker.team.manager_id == manager.pk


def _require_manage(manager, worker):
    if not can_manage(manager, worker):
        raise ServiceError("Bu ishchi sizning guruhingizda emas.")


def managed_workers(manager):
    qs = Employee.objects.filter(role=Employee.Role.WORKER, is_active=True).select_related(
        "team", "worker_type"
    )
    if manager.is_boss:
        return list(qs)
    return list(qs.filter(team__manager=manager))


def managers_of(worker):
    """Who should approve this worker's entries: the team manager, or the bosses if none."""
    if worker.team_id and worker.team.manager_id and worker.team.manager.telegram_id:
        return [worker.team.manager]
    return bosses()


# --- Catalogue --------------------------------------------------------------


def products_for(worker):
    if not worker.worker_type_id:
        return []
    return list(
        Product.objects.filter(
            is_active=True,
            operations__is_active=True,
            operations__worker_type_id=worker.worker_type_id,
        ).distinct()
    )


def operations_for(worker, product, day):
    """Operations the worker may still enter for this day (one entry per operation per day)."""
    taken = WorkEntry.objects.filter(worker=worker, date=day).exclude(
        status=WorkEntry.Status.REJECTED
    )
    return list(
        Operation.objects.filter(
            product=product, is_active=True, worker_type_id=worker.worker_type_id
        )
        .exclude(pk__in=taken.values("operation_id"))
        .select_related("product")
    )


# --- Entries ----------------------------------------------------------------


def _check_operation(worker, operation):
    if not worker.is_active or worker.role != Employee.Role.WORKER:
        raise ServiceError("Ish faqat faol ishchi uchun kiritiladi.")
    if not operation.is_active or not operation.product.is_active:
        raise ServiceError("Bu ish turi faol emas.")
    if operation.worker_type_id != worker.worker_type_id:
        raise ServiceError("Bu ish turi ishchining mutaxassisligiga mos emas.")


@transaction.atomic
def submit_entry(worker, operation, quantity, now=None):
    """A worker enters their own work. It waits for the manager's approval."""
    now = now or local_now()
    day = now.date()
    _require_open(day, now)
    _validate_quantity(quantity)
    _check_operation(worker, operation)
    existing = WorkEntry.objects.select_for_update().filter(
        worker=worker, operation=operation, date=day
    ).first()
    if existing and existing.status != WorkEntry.Status.REJECTED:
        if existing.entered_by_id != worker.pk:
            raise ServiceError("Bu ishni boshqaruvchi allaqachon kiritgan, qayta kiritib bo'lmaydi.")
        raise ServiceError("Bu ishni bugun allaqachon kiritgansiz.")
    if existing:
        existing.quantity = quantity
        existing.defect_quantity = 0
        existing.unit_price = operation.price
        existing.status = WorkEntry.Status.PENDING
        existing.entered_by = worker
        existing.approved_by = None
        existing.approved_at = None
        existing.reject_reason = ""
        existing.save()
        return get_entry(existing.pk)
    entry = WorkEntry.objects.create(
        date=day,
        worker=worker,
        operation=operation,
        quantity=quantity,
        unit_price=operation.price,
        entered_by=worker,
    )
    return get_entry(entry.pk)


@transaction.atomic
def manager_enter(manager, worker, operation, quantity, now=None):
    """A manager enters work on a worker's behalf. It counts as approved right away."""
    now = now or local_now()
    day = now.date()
    _require_manage(manager, worker)
    _require_open(day, now)
    _validate_quantity(quantity)
    _check_operation(worker, operation)
    existing = WorkEntry.objects.select_for_update().filter(
        worker=worker, operation=operation, date=day
    ).first()
    if existing and existing.status == WorkEntry.Status.PENDING:
        raise ServiceError("Ishchi bu ishni o'zi kiritgan. Uni \"Kutilayotganlar\" bo'limida tasdiqlang.")
    if existing and existing.status == WorkEntry.Status.APPROVED:
        raise ServiceError("Bu ish bugun allaqachon kiritilgan. Kerak bo'lsa, \"Tahrirlash\" orqali o'zgartiring.")
    if existing:
        existing.delete()
    entry = WorkEntry.objects.create(
        date=day,
        worker=worker,
        operation=operation,
        quantity=quantity,
        unit_price=operation.price,
        status=WorkEntry.Status.APPROVED,
        entered_by=manager,
        approved_by=manager,
        approved_at=now,
    )
    return get_entry(entry.pk)


def _entry_qs():
    return WorkEntry.objects.select_related(
        "worker", "worker__team", "operation", "operation__product", "entered_by", "approved_by"
    )


def get_entry(entry_id):
    entry = _entry_qs().filter(pk=entry_id).first()
    if not entry:
        raise ServiceError("Yozuv topilmadi.")
    return entry


def recent_entries(manager, days=7, day=None):
    """Entries of the manager's workers for the last few days, newest first."""
    day = day or today()
    qs = _entry_qs().filter(date__gt=day - dt.timedelta(days=days), date__lte=day)
    if not manager.is_boss:
        qs = qs.filter(worker__team__manager=manager)
    return list(qs.order_by("-date", "worker__full_name", "operation__name"))


def pending_for(manager):
    qs = _entry_qs().filter(status=WorkEntry.Status.PENDING, worker__is_active=True)
    if not manager.is_boss:
        qs = qs.filter(worker__team__manager=manager)
    return list(qs.order_by("date", "worker__full_name"))


@transaction.atomic
def approve(manager, entry, now=None):
    entry = WorkEntry.objects.select_for_update().select_related("worker__team").get(pk=entry.pk)
    _require_manage(manager, entry.worker)
    if entry.status != WorkEntry.Status.PENDING:
        raise ServiceError("Bu yozuv allaqachon ko'rib chiqilgan.")
    entry.status = WorkEntry.Status.APPROVED
    entry.approved_by = manager
    entry.approved_at = now or local_now()
    entry.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return get_entry(entry.pk)


def approve_all(manager, now=None):
    approved = []
    for entry in pending_for(manager):
        try:
            approved.append(approve(manager, entry, now))
        except ServiceError:
            continue
    return approved


@transaction.atomic
def reject(manager, entry, reason):
    reason = (reason or "").strip()
    if len(reason) < 3:
        raise ServiceError("Rad etish sababini yozing.")
    entry = WorkEntry.objects.select_for_update().select_related("worker__team").get(pk=entry.pk)
    _require_manage(manager, entry.worker)
    if entry.status != WorkEntry.Status.PENDING:
        raise ServiceError("Bu yozuv allaqachon ko'rib chiqilgan.")
    entry.status = WorkEntry.Status.REJECTED
    entry.reject_reason = reason
    entry.save(update_fields=["status", "reject_reason", "updated_at"])
    return get_entry(entry.pk)


@transaction.atomic
def edit_entry(manager, entry, field, new_value, comment, now=None):
    """Change the quantity or the defect count of an approved entry; a comment is required."""
    now = now or local_now()
    comment = (comment or "").strip()
    if len(comment) < 3:
        raise ServiceError("O'zgartirish uchun izoh yozish shart.")
    if field not in (EntryEdit.Field.QUANTITY, EntryEdit.Field.DEFECT):
        raise ServiceError("Noma'lum maydon.")
    entry = WorkEntry.objects.select_for_update().select_related("worker__team").get(pk=entry.pk)
    _require_manage(manager, entry.worker)
    if entry.status != WorkEntry.Status.APPROVED:
        raise ServiceError("Faqat tasdiqlangan yozuvni o'zgartirish mumkin.")
    _require_open(entry.date, now)
    if not isinstance(new_value, int) or new_value < 0:
        raise ServiceError("Qiymat manfiy bo'lmagan butun son bo'lishi kerak.")
    if field == EntryEdit.Field.QUANTITY:
        _validate_quantity(new_value)
        if new_value < entry.defect_quantity:
            raise ServiceError(f"Son brakdan ({entry.defect_quantity}) kam bo'lishi mumkin emas.")
    elif new_value > entry.quantity:
        raise ServiceError(f"Brak tikilgan sondan ({entry.quantity}) ko'p bo'lishi mumkin emas.")
    old_value = getattr(entry, field)
    if old_value == new_value:
        raise ServiceError("Yangi qiymat eskisi bilan bir xil.")
    setattr(entry, field, new_value)
    entry.save(update_fields=[field, "updated_at"])
    EntryEdit.objects.create(
        entry=entry,
        editor=manager,
        field=field,
        old_value=old_value,
        new_value=new_value,
        comment=comment,
    )
    return get_entry(entry.pk)


def editable_entries(manager, now=None):
    now = now or local_now()
    if not day_is_open(now.date(), now):
        return []
    qs = _entry_qs().filter(date=now.date(), status=WorkEntry.Status.APPROVED)
    if not manager.is_boss:
        qs = qs.filter(worker__team__manager=manager)
    return list(qs.order_by("worker__full_name", "operation__name"))


def worker_entries(worker, day):
    return list(_entry_qs().filter(worker=worker, date=day).order_by("created_at"))


def is_unusual(entry, days=30, factor=2):
    """True when the quantity is more than `factor` times this worker's usual amount for the operation."""
    since = entry.date - dt.timedelta(days=days)
    history = list(
        WorkEntry.objects.filter(
            worker_id=entry.worker_id,
            operation_id=entry.operation_id,
            status=WorkEntry.Status.APPROVED,
            date__gte=since,
            date__lt=entry.date,
        ).values_list("quantity", flat=True)
    )
    if len(history) < 3:
        return False
    average = sum(history) / len(history)
    return entry.quantity > average * factor


# --- Reports ----------------------------------------------------------------


@dataclass
class WorkerTotal:
    name: str
    team: str
    quantity: int = 0
    defect: int = 0
    amount: int = 0


@dataclass
class OperationTotal:
    product: str
    operation: str
    quantity: int = 0
    defect: int = 0
    amount: int = 0


def approved_entries(start, end, team=None, worker=None):
    qs = _entry_qs().filter(status=WorkEntry.Status.APPROVED, date__gte=start, date__lte=end)
    if team is not None:
        qs = qs.filter(worker__team=team)
    if worker is not None:
        qs = qs.filter(worker=worker)
    return list(qs.order_by("worker__full_name", "operation__product__name", "operation__name"))


def range_summary(start, end, team=None):
    by_worker = {}
    by_operation = {}
    for e in approved_entries(start, end, team=team):
        w = by_worker.setdefault(
            e.worker_id, WorkerTotal(e.worker.full_name, e.worker.team.name if e.worker.team else "-")
        )
        o = by_operation.setdefault(
            e.operation_id, OperationTotal(e.operation.product.name, e.operation.name)
        )
        for total in (w, o):
            total.quantity += e.quantity
            total.defect += e.defect_quantity
            total.amount += e.amount
    workers = sorted(by_worker.values(), key=lambda t: -t.amount)
    operations = sorted(by_operation.values(), key=lambda t: (t.product, t.operation))
    return {
        "start": start,
        "end": end,
        "workers": workers,
        "operations": operations,
        "total_amount": sum(t.amount for t in workers),
        "total_quantity": sum(t.quantity for t in workers),
        "total_defect": sum(t.defect for t in workers),
    }


def month_bounds(day):
    start = day.replace(day=1)
    next_month = (start + dt.timedelta(days=32)).replace(day=1)
    return start, next_month - dt.timedelta(days=1)


def worker_month(worker, day):
    """Approved earnings of a worker from the start of the month to `day`."""
    start, _ = month_bounds(day)
    entries = approved_entries(start, day, worker=worker)
    pending = WorkEntry.objects.filter(
        worker=worker, status=WorkEntry.Status.PENDING, date__gte=start, date__lte=day
    ).count()
    return {
        "start": start,
        "end": day,
        "quantity": sum(e.quantity for e in entries),
        "defect": sum(e.defect_quantity for e in entries),
        "amount": sum(e.amount for e in entries),
        "pending": pending,
    }


def worker_history(worker, months=6, day=None):
    """Monthly totals for the last few months, newest first."""
    day = day or today()
    rows = []
    start, end = month_bounds(day)
    for _ in range(months):
        entries = approved_entries(start, end, worker=worker)
        if entries:
            rows.append((start, sum(e.amount for e in entries), sum(e.quantity for e in entries)))
        start, end = month_bounds(start - dt.timedelta(days=1))
    return rows


def team_day_status(manager, day):
    """Per worker: approved and pending counts for the day; workers with nothing entered."""
    workers = managed_workers(manager)
    stats = defaultdict(lambda: {"approved": 0, "pending": 0})
    for e in WorkEntry.objects.filter(date=day, worker__in=workers).exclude(
        status=WorkEntry.Status.REJECTED
    ):
        stats[e.worker_id][e.status] += e.quantity
    done = [(w, stats[w.pk]) for w in workers if w.pk in stats]
    missing = [w for w in workers if w.pk not in stats]
    return done, missing


def workers_without_entries(day):
    entered = WorkEntry.objects.filter(date=day).values("worker_id")
    return list(
        Employee.objects.filter(
            role=Employee.Role.WORKER, is_active=True, telegram_id__isnull=False
        ).exclude(pk__in=entered)
    )


def edits_on(day):
    return list(
        EntryEdit.objects.filter(created_at__date=day)
        .select_related("entry__worker", "entry__operation__product", "editor")
        .order_by("editor__full_name", "created_at")
    )


def teams_with_chat():
    return list(Team.objects.filter(telegram_chat_id__isnull=False))


def teams_for(employee):
    if employee.is_boss:
        return list(Team.objects.all())
    if employee.is_manager:
        return list(Team.objects.filter(manager=employee))
    return []


def bind_team_chat(employee, team_id, chat_id):
    team = Team.objects.filter(pk=team_id).first()
    if not team or team not in teams_for(employee):
        raise ServiceError("Bu guruhni ulashga ruxsatingiz yo'q.")
    Team.objects.filter(telegram_chat_id=chat_id).exclude(pk=team.pk).update(telegram_chat_id=None)
    team.telegram_chat_id = chat_id
    team.save(update_fields=["telegram_chat_id"])
    return team
