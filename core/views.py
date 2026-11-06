"""Website for managers: their team's entries, with approve, reject and edit buttons."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core import orders, services, telegram
from core.models import Employee, EntryEdit, Operation, Order
from core.services import ServiceError


class LoginView(auth_views.LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True


def manager_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        manager = services.site_employee(request.user)
        if manager is None:
            if request.user.is_staff:
                return redirect("admin:index")
            return render(request, "core/no_access.html", status=403)
        request.manager = manager
        return view(request, *args, **kwargs)

    return wrapper


@manager_required
def dashboard(request):
    manager = request.manager
    day = services.today()
    roster = services.team_roster(manager, day)
    return render(
        request,
        "core/dashboard.html",
        {
            "manager": manager,
            "teams": services.teams_for(manager),
            "day": day,
            "day_open": services.day_is_open(day),
            "pending": services.pending_for(manager),
            "editable": {e.pk for e in services.editable_entries(manager)},
            "recent": services.recent_entries(manager),
            "roster": roster,
            "missing": [r.worker for r in roster if not r.entries],
            "fields": EntryEdit.Field.choices,
        },
    )


def _entry_of(request):
    entry = services.get_entry(int(request.POST.get("entry", 0)))
    if not services.can_manage(request.manager, entry.worker):
        raise ServiceError("Bu ishchi sizning guruhingizda emas.")
    return entry


def _action(view):
    """POST-only manager action: show ServiceError as a message and go back to the dashboard."""

    @manager_required
    @require_POST
    @wraps(view)
    def wrapper(request):
        try:
            text = view(request)
        except ServiceError as err:
            messages.error(request, str(err))
        else:
            messages.success(request, text)
        return redirect("dashboard")

    return wrapper


@_action
def approve(request):
    entry = services.approve(request.manager, _entry_of(request))
    telegram.tell_worker(entry, "you_approved")
    return f"Tasdiqlandi: {entry.worker}, {entry.operation}, {entry.quantity} dona."


@_action
def approve_all(request):
    approved = services.approve_all(request.manager)
    for entry in approved:
        telegram.tell_worker(entry, "you_approved")
    return f"{len(approved)} ta yozuv tasdiqlandi."


@_action
def reject(request):
    entry = services.reject(request.manager, _entry_of(request), request.POST.get("reason"))
    telegram.tell_worker(entry, "you_rejected", reason=entry.reject_reason)
    return f"Rad etildi: {entry.worker}, {entry.operation}."


@_action
def edit(request):
    try:
        value = int(request.POST.get("value", ""))
    except ValueError:
        raise ServiceError("Qiymat butun son bo'lishi kerak.")
    entry = _entry_of(request)
    field = request.POST.get("field")
    if field not in dict(EntryEdit.Field.choices):
        raise ServiceError("Noma'lum maydon.")
    old = getattr(entry, field)
    entry = services.edit_entry(request.manager, entry, field, value, request.POST.get("comment"))
    telegram.tell_worker(
        entry,
        "edited_for_you",
        manager=request.manager.full_name,
        field=telegram.field_label(field, entry.worker.script),
        old=old,
        new=value,
        comment=request.POST.get("comment", "").strip(),
    )
    label = dict(EntryEdit.Field.choices)[field]
    return f"O'zgartirildi: {entry.worker}, {entry.operation}: {label.lower()} {old} → {value}."



def _int(value, message):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ServiceError(message)


@_action
def enter(request):
    """The manager enters a worker's work for today; it is approved right away."""
    worker = Employee.objects.select_related("team").filter(
        pk=_int(request.POST.get("worker"), "Ishchini tanlang.")
    ).first()
    if worker is None or not services.can_manage(request.manager, worker):
        raise ServiceError("Bu ishchi sizning guruhingizda emas.")
    operation = Operation.objects.select_related("product").filter(
        pk=_int(request.POST.get("operation"), "Ishni tanlang.")
    ).first()
    if operation is None:
        raise ServiceError("Ishni tanlang.")
    quantity = _int(request.POST.get("quantity"), "Son butun son bo'lishi kerak.")
    entry = services.manager_enter(request.manager, worker, operation, quantity)
    telegram.tell_worker(entry, "entered_for_you", manager=request.manager.full_name)
    return f"Kiritildi: {entry.worker}, {entry.operation}, {entry.quantity} dona."


@manager_required
def order_list(request):
    """All orders with their progress; open ones first. Read-only: the boss manages orders in the admin."""
    show_closed = request.GET.get("hammasi") == "1"
    qs = Order.objects.select_related("product")
    if not show_closed:
        qs = qs.filter(status__in=Order.OPEN_STATUSES + (Order.Status.DONE,))
    items = [orders.progress(o, request.manager) for o in qs]
    items.sort(key=lambda p: (not p.order.is_open, p.order.deadline is None, p.order.deadline or services.today(), p.order.pk))
    return render(
        request,
        "core/orders/list.html",
        {"manager": request.manager, "items": items, "show_closed": show_closed},
    )


@manager_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("product"), pk=pk)
    return render(
        request, "core/orders/detail.html", {"manager": request.manager, "p": orders.progress(order, request.manager)}
    )
