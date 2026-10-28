import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.state import State, StatesGroup
from asgiref.sync import sync_to_async
from django.db import close_old_connections

from bot.texts import t
from core import services
from core.translit import to_cyrillic

log = logging.getLogger(__name__)


class EntryForm(StatesGroup):
    quantity = State()
    confirm = State()


class RejectForm(StatesGroup):
    reason = State()


class EditForm(StatesGroup):
    value = State()
    comment = State()


class RangeForm(StatesGroup):
    dates = State()


def _with_fresh_connection(fn, *args, **kwargs):
    # The bot runs for days; drop database connections that the server has closed.
    close_old_connections()
    return fn(*args, **kwargs)


def run(fn, *args, **kwargs):
    """Run synchronous ORM code from a handler."""
    return sync_to_async(_with_fresh_connection)(fn, *args, **kwargs)


async def current_employee(telegram_id):
    return await run(services.get_by_telegram, telegram_id)


def error_text(err, script):
    text = str(err)
    return to_cyrillic(text) if script == "cyrillic" else text


async def notify(bot: Bot, chat_id, text, reply_markup=None):
    if not chat_id:
        return
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except TelegramAPIError as exc:
        log.warning("Could not notify %s: %s", chat_id, exc)


def entry_fields(entry):
    """Common format arguments for texts describing an entry."""
    from core.reports import fmt_date, money

    return {
        "worker": entry.worker.full_name,
        "product": entry.operation.product.name,
        "operation": entry.operation.name,
        "qty": entry.quantity,
        "defect": entry.defect_quantity,
        "amount": money(entry.amount),
        "date": fmt_date(entry.date),
    }


def status_text(entry, script):
    return t(f"status_{entry.status}", script)


async def reset_state_on_menu(handler, event, data):
    """Pressing a menu button abandons whatever form the user was filling in."""
    from bot.texts import menu_texts

    state = data.get("state")
    if state is not None and getattr(event, "text", None) in menu_texts():
        await state.clear()
        data["raw_state"] = None
    return await handler(event, data)
