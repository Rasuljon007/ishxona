"""Website for managers: their team's entries, with approve, reject and edit buttons."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core import services, telegram
from core.models import EntryEdit
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
    done, missing = services.team_day_status(manager, day)
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
            "done": done,
            "missing": missing,
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
    label = dict(EntryEdit.Field.choices)[field]
    return f"O'zgartirildi: {entry.worker}, {entry.operation}: {label.lower()} {old} → {value}."

