from aiogram.filters.callback_data import CallbackData
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.texts import t
from core.models import Employee
from core.reports import money


class ScriptCb(CallbackData, prefix="s"):
    script: str


class WorkerCb(CallbackData, prefix="w"):
    worker_id: int


class ProductCb(CallbackData, prefix="p"):
    product_id: int


class OperationCb(CallbackData, prefix="o"):
    operation_id: int


class ConfirmCb(CallbackData, prefix="c"):
    ok: bool


class EntryCb(CallbackData, prefix="e"):
    action: str  # ok | no | edit
    entry_id: int


class FieldCb(CallbackData, prefix="f"):
    entry_id: int
    field: str  # quantity | defect_quantity


class ApproveAllCb(CallbackData, prefix="aa"):
    pass


class TeamBindCb(CallbackData, prefix="tb"):
    team_id: int


def script_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Lotin", callback_data=ScriptCb(script=Employee.Script.LATIN))
    kb.button(text="Кирилл", callback_data=ScriptCb(script=Employee.Script.CYRILLIC))
    return kb.as_markup()


def contact_kb(script):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("send_contact", script), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_menu(employee):
    s = employee.script
    if employee.is_boss:
        rows = [
            ["btn_rep_today", "btn_rep_week"],
            ["btn_rep_month", "btn_rep_range"],
            ["btn_pending", "btn_enter_for"],
            ["btn_edit", "btn_team_today"],
            ["btn_script"],
        ]
    elif employee.is_manager:
        rows = [
            ["btn_pending", "btn_enter_for"],
            ["btn_edit", "btn_team_today"],
            ["btn_script"],
        ]
    else:
        rows = [
            ["btn_enter"],
            ["btn_my_today", "btn_my_month"],
            ["btn_history", "btn_script"],
        ]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(k, s)) for k in row] for row in rows],
        resize_keyboard=True,
    )


def workers_kb(workers):
    kb = InlineKeyboardBuilder()
    for w in workers:
        label = f"{w.full_name} ({w.worker_type.name})" if w.worker_type else w.full_name
        kb.button(text=label, callback_data=WorkerCb(worker_id=w.pk))
    kb.adjust(1)
    return kb.as_markup()


def products_kb(products):
    kb = InlineKeyboardBuilder()
    for p in products:
        kb.button(text=p.name, callback_data=ProductCb(product_id=p.pk))
    kb.adjust(2)
    return kb.as_markup()


def operations_kb(operations):
    kb = InlineKeyboardBuilder()
    for o in operations:
        kb.button(text=f"{o.name} · {money(o.price)}", callback_data=OperationCb(operation_id=o.pk))
    kb.adjust(1)
    return kb.as_markup()


def confirm_kb(script):
    kb = InlineKeyboardBuilder()
    kb.button(text=t("yes", script), callback_data=ConfirmCb(ok=True))
    kb.button(text=t("no", script), callback_data=ConfirmCb(ok=False))
    kb.adjust(1)
    return kb.as_markup()


def review_kb(entry_id, script):
    kb = InlineKeyboardBuilder()
    kb.button(text=t("btn_approve", script), callback_data=EntryCb(action="ok", entry_id=entry_id))
    kb.button(text=t("btn_reject", script), callback_data=EntryCb(action="no", entry_id=entry_id))
    return kb.as_markup()


def approve_all_kb(count, script):
    kb = InlineKeyboardBuilder()
    kb.button(text=t("btn_approve_all", script, count=count), callback_data=ApproveAllCb())
    return kb.as_markup()


def editable_kb(entries):
    kb = InlineKeyboardBuilder()
    for e in entries:
        label = f"{e.worker.full_name}: {e.operation.name} {e.quantity}"
        if e.defect_quantity:
            label += f" (brak {e.defect_quantity})"
        kb.button(text=label, callback_data=EntryCb(action="edit", entry_id=e.pk))
    kb.adjust(1)
    return kb.as_markup()


def field_kb(entry_id, script):
    kb = InlineKeyboardBuilder()
    kb.button(text=t("btn_field_qty", script), callback_data=FieldCb(entry_id=entry_id, field="quantity"))
    kb.button(
        text=t("btn_field_defect", script), callback_data=FieldCb(entry_id=entry_id, field="defect_quantity")
    )
    kb.adjust(1)
    return kb.as_markup()


def teams_kb(teams):
    kb = InlineKeyboardBuilder()
    for team in teams:
        kb.button(text=team.name, callback_data=TeamBindCb(team_id=team.pk))
    kb.adjust(1)
    return kb.as_markup()
