"""Entering work: a worker for themselves, or a manager on a worker's behalf."""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot.texts import t, variants
from bot.utils import EntryForm, current_employee, entry_fields, error_text, notify, run
from core import services
from core.models import Employee, Operation, Product
from core.reports import money

router = Router()
router.message.filter(F.chat.type == "private")


def _load_worker(worker_id):
    return Employee.objects.select_related("team", "team__manager", "worker_type").get(pk=worker_id)


def _load_operation(operation_id):
    return Operation.objects.select_related("product").get(pk=operation_id)


async def _start_products(target, actor, send, state: FSMContext):
    script = actor.script
    if not target.worker_type_id:
        await send(t("no_worker_type", script))
        return
    products = await run(services.products_for, target)
    if not products:
        await send(t("no_products", script))
        return
    await state.set_state(None)
    await state.set_data({"worker_id": target.pk})
    await send(t("choose_product", script), reply_markup=kb.products_kb(products))


@router.message(F.text.in_(variants("btn_enter")))
async def enter_self(message: Message, state: FSMContext):
    employee = await current_employee(message.from_user.id)
    if not employee or not employee.is_active or employee.role != Employee.Role.WORKER:
        return
    await _start_products(employee, employee, message.answer, state)


@router.message(F.text.in_(variants("btn_enter_for")))
async def enter_for(message: Message, state: FSMContext):
    employee = await current_employee(message.from_user.id)
    if not employee or not employee.is_active or not (employee.is_manager or employee.is_boss):
        return
    workers = await run(services.managed_workers, employee)
    if not workers:
        await message.answer(t("no_workers", employee.script))
        return
    await state.clear()
    await message.answer(t("choose_worker", employee.script), reply_markup=kb.workers_kb(workers))


@router.callback_query(kb.WorkerCb.filter())
async def worker_chosen(query: CallbackQuery, callback_data: kb.WorkerCb, state: FSMContext):
    await query.answer()
    actor = await current_employee(query.from_user.id)
    if not actor or not actor.is_active:
        return
    worker = await run(_load_worker, callback_data.worker_id)
    if not await run(services.can_manage, actor, worker):
        return
    await _start_products(worker, actor, query.message.answer, state)


@router.callback_query(kb.ProductCb.filter())
async def product_chosen(query: CallbackQuery, callback_data: kb.ProductCb, state: FSMContext):
    await query.answer()
    actor = await current_employee(query.from_user.id)
    data = await state.get_data()
    if not actor or "worker_id" not in data:
        return
    worker = await run(_load_worker, data["worker_id"])
    product = await run(Product.objects.get, pk=callback_data.product_id)
    operations = await run(services.operations_for, worker, product, services.today())
    if not operations:
        await query.message.answer(t("all_entered", actor.script))
        return
    await query.message.edit_text(
        t("choose_operation", actor.script, product=product.name), reply_markup=kb.operations_kb(operations)
    )


@router.callback_query(kb.OperationCb.filter())
async def operation_chosen(query: CallbackQuery, callback_data: kb.OperationCb, state: FSMContext):
    await query.answer()
    actor = await current_employee(query.from_user.id)
    data = await state.get_data()
    if not actor or "worker_id" not in data:
        return
    worker = await run(_load_worker, data["worker_id"])
    operation = await run(_load_operation, callback_data.operation_id)
    await state.update_data(operation_id=operation.pk)
    await state.set_state(EntryForm.quantity)
    fields = dict(product=operation.product.name, operation=operation.name, price=money(operation.price))
    if worker.pk == actor.pk:
        text = t("ask_quantity", actor.script, **fields)
    else:
        text = t("ask_quantity_for", actor.script, worker=worker.full_name, **fields)
    await query.message.edit_text(text)


@router.message(EntryForm.quantity)
async def quantity_entered(message: Message, state: FSMContext):
    actor = await current_employee(message.from_user.id)
    if not actor:
        return
    raw = (message.text or "").strip().replace(" ", "")
    if not raw.isdigit() or int(raw) < 1:
        await message.answer(t("bad_number", actor.script))
        return
    qty = int(raw)
    data = await state.get_data()
    worker = await run(_load_worker, data["worker_id"])
    operation = await run(_load_operation, data["operation_id"])
    await state.update_data(quantity=qty)
    await state.set_state(EntryForm.confirm)
    fields = dict(product=operation.product.name, operation=operation.name, qty=qty)
    if worker.pk == actor.pk:
        text = t("confirm_self", actor.script, **fields)
    else:
        text = t("confirm_for", actor.script, worker=worker.full_name, **fields)
    await message.answer(text, reply_markup=kb.confirm_kb(actor.script))


@router.callback_query(EntryForm.confirm, kb.ConfirmCb.filter())
async def entry_confirmed(query: CallbackQuery, callback_data: kb.ConfirmCb, state: FSMContext, bot: Bot):
    await query.answer()
    actor = await current_employee(query.from_user.id)
    data = await state.get_data()
    await state.clear()
    await query.message.edit_reply_markup(reply_markup=None)
    if not actor:
        return
    if not callback_data.ok:
        await query.message.answer(t("cancelled", actor.script))
        return
    worker = await run(_load_worker, data["worker_id"])
    operation = await run(_load_operation, data["operation_id"])
    try:
        if worker.pk == actor.pk:
            entry = await run(services.submit_entry, worker, operation, data["quantity"])
        else:
            entry = await run(services.manager_enter, actor, worker, operation, data["quantity"])
    except services.ServiceError as err:
        await query.message.answer(error_text(err, actor.script))
        return

    fields = entry_fields(entry)
    if worker.pk == actor.pk:
        await query.message.answer(t("sent_for_approval", actor.script))
        unusual = await run(services.is_unusual, entry)
        for manager in await run(services.managers_of, worker):
            text = t("new_entry", manager.script, **fields)
            if unusual:
                text += "\n" + t("unusual", manager.script)
            await notify(bot, manager.telegram_id, text, kb.review_kb(entry.pk, manager.script))
    else:
        await query.message.answer(t("entered_for", actor.script))
        await notify(
            bot, worker.telegram_id, t("entered_for_you", worker.script, manager=actor.full_name, **fields)
        )
