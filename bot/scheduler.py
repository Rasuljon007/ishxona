"""Daily jobs: reminders before closing time and the reports at closing time."""

import asyncio
import datetime as dt
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile
from django.conf import settings
from django.utils import timezone

from bot.texts import t
from bot.utils import notify, run
from core import reports, services
from core.reports import fmt_date

log = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4000


def next_run(now):
    """The next (time, job) after `now`."""
    candidates = []
    for days in (0, 1):
        day = now.date() + dt.timedelta(days=days)
        for hour, job in ((settings.REMINDER_HOUR, "reminders"), (settings.DAY_CLOSE_HOUR, "reports")):
            at = timezone.make_aware(dt.datetime.combine(day, dt.time(hour)), now.tzinfo)
            if at > now:
                candidates.append((at, job))
    return min(candidates)


async def send_reminders(bot: Bot, day):
    for worker in await run(services.workers_without_entries, day):
        await notify(bot, worker.telegram_id, t("reminder", worker.script, hour=settings.DAY_CLOSE_HOUR))
    managers = await run(lambda: list(services.Employee.objects.filter(
        role__in=[services.Employee.Role.MANAGER, services.Employee.Role.BOSS],
        is_active=True,
        telegram_id__isnull=False,
    )))
    for manager in managers:
        count = len(await run(services.pending_for, manager))
        if count:
            await notify(bot, manager.telegram_id, t("manager_reminder", manager.script, count=count, hour=settings.DAY_CLOSE_HOUR))


def _chunks(lines):
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > TELEGRAM_LIMIT:
            yield chunk
            chunk = ""
        chunk += line + "\n"
    if chunk:
        yield chunk


async def send_daily_reports(bot: Bot, day):
    for team in await run(services.teams_with_chat):
        pdf = await run(reports.team_daily_pdf, team, day)
        if not pdf:
            continue
        try:
            await bot.send_document(
                team.telegram_chat_id,
                BufferedInputFile(pdf, filename=f"{team.name}_{day:%Y%m%d}.pdf"),
                caption=t("daily_caption", team=team.name, date=fmt_date(day)),
            )
        except TelegramAPIError as exc:
            log.warning("Daily report for %s failed: %s", team, exc)

    edits = await run(services.edits_on, day)
    summary = await run(reports.summary_pdf, day, day)
    for boss in await run(services.bosses):
        s = boss.script
        if edits:
            lines = [t("edits_head", s, date=fmt_date(day))]
            for e in edits:
                lines.append(
                    t(
                        "edits_row",
                        s,
                        editor=e.editor.full_name,
                        worker=e.entry.worker.full_name,
                        product=e.entry.operation.product.name,
                        operation=e.entry.operation.name,
                        field=t(f"field_{e.field}", s),
                        old=e.old_value,
                        new=e.new_value,
                        time=timezone.localtime(e.created_at).strftime("%H:%M"),
                        comment=e.comment,
                    )
                )
            for chunk in _chunks(lines):
                await notify(bot, boss.telegram_id, chunk)
        else:
            await notify(bot, boss.telegram_id, t("edits_none", s, date=fmt_date(day)))
        try:
            await bot.send_document(
                boss.telegram_id,
                BufferedInputFile(summary, filename=f"umumiy_{day:%Y%m%d}.pdf"),
                caption=t("daily_boss_caption", s, date=fmt_date(day)),
            )
        except TelegramAPIError as exc:
            log.warning("Boss report failed: %s", exc)


async def daily_loop(bot: Bot):
    while True:
        now = timezone.localtime()
        at, job = next_run(now)
        await asyncio.sleep((at - now).total_seconds())
        try:
            if job == "reminders":
                await send_reminders(bot, at.date())
            else:
                await send_daily_reports(bot, at.date())
        except Exception:
            log.exception("Daily job %s failed", job)
