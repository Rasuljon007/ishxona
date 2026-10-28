"""Approving, rejecting and editing entries (managers and the boss)."""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot.texts import t, variants
from bot.utils import EditForm, RejectForm, current_employee, entry_fields, error_text, notify, run
from core import services
from core.models import EntryEdit
from core.reports import fmt_date

router = Router()

PENDING_LIST_LIMIT = 20


async def _manager(user_id):
    employee = await current_employee(user_id)
    if employee and employee.is_active and (employee.is_manager or employee.is_boss):
        return employee
    return None


def _field_label(field, script):
    return t(f"field_{field}", script)


@router.message(F.chat.type == "private", F.text.in_(variants("btn_pending")))
async def pending(message: Message):
    manager = await _manager(message.from_user.id)
    if not manager:
        return
    entries = await run(services.pending_for, manager)
    if not entries:
        await message.answer(t("no_pending", manager.script))
        return
    await message.answer(t("pending_count", manager.script, count=len(entries)))
    for entry in entries[:PENDING_LIST_LIMIT]:
        await message.answer(
            t("new_entry", manager.script, **entry_fields(entry)), reply_markup=kb.review_kb(entry.pk, manager.script)
        )
    if len(entries) > 1:
        await message.answer(
            t("pending_count", manager.script, count=len(entries)),
            reply_markup=kb.approve_all_kb(len(entries), manager.script),
        )


async def _tell_approved(bot, entry):
    worker = entry.worker
    await notify(bot, worker.telegram_id, t("you_approved", worker.script, **entry_fields(entry)))


@router.callback_query(kb.EntryCb.filter(F.action == "ok"))
async def approve(query: CallbackQuery, callback_data: kb.EntryCb, bot: Bot):
    manager = await _manager(query.from_user.id)
    if not manager:
        await query.answer()
        return
    try:
        entry = await run(services.get_entry, callback_data.entry_id)
        entry = await run(services.approve, manager, entry)
    except services.ServiceError as err:
        await query.answer(error_text(err, manager.script), show_alert=True)
        return
    await query.answer()
    await query.message.edit_text(
        query.message.html_text + "\n\n" + t("approved_mark", manager.script, by=manager.full_name)
    )
    await _tell_approved(bot, entry)


@router.callback_query(kb.ApproveAllCb.filter())
async def approve_all(query: CallbackQuery, bot: Bot):
    manager = await _manager(query.from_user.id)
    await query.answer()
    if not manager:
        return
    approved = await run(services.approve_all, manager)
    await query.message.edit_text(t("approved_all", manager.script, count=len(approved)))
    for entry in approved:
        await _tell_approved(bot, entry)


@router.callback_query(kb.EntryCb.filter(F.action == "no"))
async def reject_start(query: CallbackQuery, callback_data: kb.EntryCb, state: FSMContext):
    await query.answer()
    manager = await _manager(query.from_user.id)
    if not manager:
        return
    await state.set_state(RejectForm.reason)
    await state.set_data({"entry_id": callback_data.entry_id})
    await query.message.answer(t("ask_reject_reason", manager.script))


@router.message(F.chat.type == "private", RejectForm.reason)
async def reject_reason(message: Message, state: FSMContext, bot: Bot):
    manager = await _manager(message.from_user.id)
    if not manager:
        return
    data = await state.get_data()
    try:
        entry = await run(services.get_entry, data["entry_id"])
        entry = await run(services.reject, manager, entry, message.text)
    except services.ServiceError as err:
        await message.answer(error_text(err, manager.script))
        return
    await state.clear()
    await message.answer(
        t("rejected_mark", manager.script, by=manager.full_name, reason=entry.reject_reason)
    )
    worker = entry.worker
    await notify(
        bot, worker.telegram_id, t("you_rejected", worker.script, reason=entry.reject_reason, **entry_fields(entry))
    )


@router.message(F.chat.type == "private", F.text.in_(variants("btn_edit")))
async def edit_list(message: Message, state: FSMContext):
    manager = await _manager(message.from_user.id)
    if not manager:
        return
    await state.clear()
    entries = await run(services.editable_entries, manager)
    if not entries:
        await message.answer(t("no_editable", manager.script))
        return
    await message.answer(t("choose_entry", manager.script), reply_markup=kb.editable_kb(entries))


@router.callback_query(kb.EntryCb.filter(F.action == "edit"))
async def edit_choose_field(query: CallbackQuery, callback_data: kb.EntryCb):
    await query.answer()
    manager = await _manager(query.from_user.id)
    if not manager:
        return
    entry = await run(services.get_entry, callback_data.entry_id)
    await query.message.edit_text(
        t("choose_field", manager.script, **entry_fields(entry)), reply_markup=kb.field_kb(entry.pk, manager.script)
    )


@router.callback_query(kb.FieldCb.filter())
async def edit_ask_value(query: CallbackQuery, callback_data: kb.FieldCb, state: FSMContext):
    await query.answer()
    manager = await _manager(query.from_user.id)
    if not manager:
        return
    entry = await run(services.get_entry, callback_data.entry_id)
    await state.set_state(EditForm.value)
    await state.set_data({"entry_id": entry.pk, "field": callback_data.field})
    if callback_data.field == EntryEdit.Field.DEFECT:
        await query.message.answer(t("ask_new_defect", manager.script, max=entry.quantity))
    else:
        await query.message.answer(t("ask_new_qty", manager.script))


@router.message(F.chat.type == "private", EditForm.value)
async def edit_value(message: Message, state: FSMContext):
    manager = await _manager(message.from_user.id)
    if not manager:
        return
    raw = (message.text or "").strip().replace(" ", "")
    if not raw.isdigit():
        await message.answer(t("bad_number", manager.script))
        return
    await state.update_data(value=int(raw))
    await state.set_state(EditForm.comment)
    await message.answer(t("ask_comment", manager.script))


@router.message(F.chat.type == "private", EditForm.comment)
async def edit_comment(message: Message, state: FSMContext, bot: Bot):
    manager = await _manager(message.from_user.id)
    if not manager:
        return
    data = await state.get_data()
    try:
        entry = await run(services.get_entry, data["entry_id"])
        old = getattr(entry, data["field"])
        entry = await run(services.edit_entry, manager, entry, data["field"], data["value"], message.text)
    except services.ServiceError as err:
        await message.answer(error_text(err, manager.script))
        if "izoh" not in str(err).lower():
            await state.clear()
        return
    await state.clear()
    new = getattr(entry, data["field"])
    await message.answer(
        t("edit_saved", manager.script, field=_field_label(data["field"], manager.script), old=old, new=new)
    )
    worker = entry.worker
    await notify(
        bot,
        worker.telegram_id,
        t(
            "edited_for_you",
            worker.script,
            manager=manager.full_name,
            field=_field_label(data["field"], worker.script),
            old=old,
            new=new,
            comment=message.text.strip(),
            **entry_fields(entry),
        ),
    )


@router.message(F.chat.type == "private", F.text.in_(variants("btn_team_today")))
async def team_today(message: Message):
    manager = await _manager(message.from_user.id)
    if not manager:
        return
    day = services.today()
    done, missing = await run(services.team_day_status, manager, day)
    lines = [t("team_status_head", manager.script, date=fmt_date(day))]
    for worker, stat in done:
        lines.append(
            t("team_status_row", manager.script, name=worker.full_name, approved=stat["approved"], pending=stat["pending"])
        )
    if missing:
        lines.append("")
        lines.append(t("team_missing", manager.script, names=", ".join(w.full_name for w in missing)))
    await message.answer("\n".join(lines))
