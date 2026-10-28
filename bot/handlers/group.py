"""Linking a Telegram group to a team so daily reports go there."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot.texts import t
from bot.utils import current_employee, error_text, run
from core import services

router = Router()


@router.message(Command("ulash"), F.chat.type.in_({"group", "supergroup"}))
async def bind_start(message: Message):
    employee = await current_employee(message.from_user.id)
    teams = await run(services.teams_for, employee) if employee and employee.is_active else []
    if not teams:
        await message.reply(t("bind_no_rights"))
        return
    await message.reply(t("bind_choose", employee.script), reply_markup=kb.teams_kb(teams))


@router.callback_query(kb.TeamBindCb.filter(), F.message.chat.type.in_({"group", "supergroup"}))
async def bind_done(query: CallbackQuery, callback_data: kb.TeamBindCb):
    employee = await current_employee(query.from_user.id)
    if not employee or not employee.is_active:
        await query.answer(t("bind_no_rights"), show_alert=True)
        return
    try:
        team = await run(services.bind_team_chat, employee, callback_data.team_id, query.message.chat.id)
    except services.ServiceError as err:
        await query.answer(error_text(err, employee.script), show_alert=True)
        return
    await query.answer()
    await query.message.edit_text(t("bind_done", team=team.name))
