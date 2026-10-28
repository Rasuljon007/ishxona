"""Worker's own earnings and the boss's reports."""

import datetime as dt
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message

from bot.texts import t, variants
from bot.utils import RangeForm, current_employee, run, status_text
from core import reports, services
from core.models import Employee
from core.reports import fmt_date, money

router = Router()
router.message.filter(F.chat.type == "private")

REPORT_TOP = 15


async def _worker(user_id):
    employee = await current_employee(user_id)
    if employee and employee.is_active and employee.role == Employee.Role.WORKER:
        return employee
    return None


async def _boss(user_id):
    employee = await current_employee(user_id)
    if employee and employee.is_active and employee.is_boss:
        return employee
    return None


@router.message(F.text.in_(variants("btn_my_today")))
async def my_today(message: Message):
    worker = await _worker(message.from_user.id)
    if not worker:
        return
    day = services.today()
    entries = await run(services.worker_entries, worker, day)
    if not entries:
        await message.answer(t("my_today_empty", worker.script))
        return
    lines = [t("my_today_head", worker.script, date=fmt_date(day))]
    for e in entries:
        lines.append(
            t(
                "my_today_row",
                worker.script,
                product=e.operation.product.name,
                operation=e.operation.name,
                qty=e.quantity,
                defect=e.defect_quantity,
                status=status_text(e, worker.script),
            )
        )
    await message.answer("\n".join(lines))


@router.message(F.text.in_(variants("btn_my_month")))
async def my_month(message: Message):
    worker = await _worker(message.from_user.id)
    if not worker:
        return
    data = await run(services.worker_month, worker, services.today())
    text = t(
        "my_month",
        worker.script,
        start=fmt_date(data["start"]),
        end=fmt_date(data["end"]),
        qty=data["quantity"],
        defect=data["defect"],
        amount=money(data["amount"]),
    )
    if data["pending"]:
        text += "\n" + t("my_month_pending", worker.script, count=data["pending"])
    await message.answer(text)


@router.message(F.text.in_(variants("btn_history")))
async def history(message: Message):
    worker = await _worker(message.from_user.id)
    if not worker:
        return
    rows = await run(services.worker_history, worker)
    if not rows:
        await message.answer(t("history_empty", worker.script))
        return
    lines = [t("history_head", worker.script)]
    for month_start, amount, qty in rows:
        lines.append(t("history_row", worker.script, month=month_start.strftime("%m.%Y"), qty=qty, amount=money(amount)))
    await message.answer("\n".join(lines))


async def send_summary(message: Message, boss, start, end):
    data = await run(services.range_summary, start, end)
    pdf = await run(reports.summary_pdf, start, end)
    period = fmt_date(start) if start == end else f"{fmt_date(start)} – {fmt_date(end)}"
    lines = [
        t(
            "report_head",
            boss.script,
            period=period,
            qty=data["total_quantity"],
            defect=data["total_defect"],
            amount=money(data["total_amount"]),
        )
    ]
    for i, w in enumerate(data["workers"][:REPORT_TOP], 1):
        lines.append(t("report_row", boss.script, i=i, name=w.name, team=w.team, qty=w.quantity, amount=money(w.amount)))
    if len(data["workers"]) > REPORT_TOP:
        lines.append(t("report_more", boss.script))
    await message.answer("\n".join(lines))
    name = f"hisobot_{start:%Y%m%d}_{end:%Y%m%d}.pdf"
    await message.answer_document(BufferedInputFile(pdf, filename=name))


@router.message(F.text.in_(variants("btn_rep_today")))
async def report_today(message: Message):
    boss = await _boss(message.from_user.id)
    if boss:
        day = services.today()
        await send_summary(message, boss, day, day)


@router.message(F.text.in_(variants("btn_rep_week")))
async def report_week(message: Message):
    boss = await _boss(message.from_user.id)
    if boss:
        day = services.today()
        await send_summary(message, boss, day - dt.timedelta(days=day.weekday()), day)


@router.message(F.text.in_(variants("btn_rep_month")))
async def report_month(message: Message):
    boss = await _boss(message.from_user.id)
    if boss:
        day = services.today()
        await send_summary(message, boss, day.replace(day=1), day)


@router.message(F.text.in_(variants("btn_rep_range")))
async def report_range_start(message: Message, state: FSMContext):
    boss = await _boss(message.from_user.id)
    if boss:
        await state.set_state(RangeForm.dates)
        await message.answer(t("ask_range", boss.script))


def parse_range(text):
    found = re.findall(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text or "")
    if len(found) != 2:
        return None
    try:
        start, end = (dt.date(int(y), int(m), int(d)) for d, m, y in found)
    except ValueError:
        return None
    return (start, end) if start <= end else (end, start)


@router.message(RangeForm.dates)
async def report_range(message: Message, state: FSMContext):
    boss = await _boss(message.from_user.id)
    if not boss:
        return
    parsed = parse_range(message.text)
    if not parsed:
        await message.answer(t("bad_range", boss.script))
        return
    await state.clear()
    await send_summary(message, boss, *parsed)
