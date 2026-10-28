from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot import keyboards as kb
from bot.texts import t, variants
from bot.utils import current_employee, error_text, notify, run
from core import services

router = Router()
router.message.filter(F.chat.type == "private")


async def show_menu(message: Message, employee):
    await message.answer(t("welcome", employee.script, name=employee.full_name), reply_markup=kb.main_menu(employee))


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    employee = await current_employee(message.from_user.id)
    if employee and employee.is_active:
        await show_menu(message, employee)
    elif employee:
        await message.answer(t("not_active", employee.script))
    else:
        await message.answer(t("choose_script"), reply_markup=kb.script_kb())


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    employee = await current_employee(message.from_user.id)
    script = employee.script if employee else "latin"
    markup = kb.main_menu(employee) if employee and employee.is_active else None
    await message.answer(t("cancelled", script), reply_markup=markup)


@router.message(F.text.in_(variants("btn_script")))
async def ask_script(message: Message):
    await message.answer(t("choose_script"), reply_markup=kb.script_kb())


@router.callback_query(kb.ScriptCb.filter())
async def choose_script(query: CallbackQuery, callback_data: kb.ScriptCb, state: FSMContext):
    script = callback_data.script
    employee = await current_employee(query.from_user.id)
    await query.answer()
    if employee:
        await run(services.set_script, employee, script)
        if employee.is_active:
            await query.message.answer(t("script_saved", script), reply_markup=kb.main_menu(employee))
        else:
            await query.message.answer(t("not_active", script))
        return
    await state.update_data(script=script)
    await query.message.answer(t("ask_contact", script), reply_markup=kb.contact_kb(script))


@router.message(F.contact)
async def got_contact(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    script = data.get("script", "latin")
    if message.contact.user_id != message.from_user.id:
        await message.answer(t("own_contact_only", script))
        return
    full_name = " ".join(
        p for p in (message.contact.first_name, message.contact.last_name) if p
    ) or message.from_user.full_name
    try:
        employee, is_new = await run(
            services.register_by_contact, message.from_user.id, message.contact.phone_number, full_name
        )
    except services.ServiceError as err:
        await message.answer(error_text(err, script), reply_markup=ReplyKeyboardRemove())
        return
    await state.clear()
    if employee.script != script:
        await run(services.set_script, employee, script)
    if is_new:
        await message.answer(t("registered_wait", script), reply_markup=ReplyKeyboardRemove())
        for boss in await run(services.bosses):
            await notify(
                bot, boss.telegram_id, t("new_worker_for_boss", boss.script, name=employee.full_name, phone=employee.phone)
            )
    elif not employee.is_active:
        await message.answer(t("not_active", script), reply_markup=ReplyKeyboardRemove())
    else:
        await show_menu(message, employee)
