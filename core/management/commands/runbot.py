import asyncio
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Telegram botni ishga tushiradi (polling) va kunlik hisobotlarni rejalashtiradi."

    def handle(self, *args, **options):
        if not settings.BOT_TOKEN:
            raise CommandError("BOT_TOKEN muhit o'zgaruvchisi berilmagan.")
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        asyncio.run(self.main())

    async def main(self):
        from aiogram import Bot, Dispatcher
        from aiogram.client.default import DefaultBotProperties
        from aiogram.fsm.storage.memory import MemoryStorage

        from bot.handlers import common, entry, group, manager, reports
        from bot.scheduler import daily_loop
        from bot.utils import reset_state_on_menu

        bot = Bot(settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
        dp = Dispatcher(storage=MemoryStorage())
        dp.message.outer_middleware(reset_state_on_menu)
        # common before the form routers so /start and /cancel work in the middle of a form.
        dp.include_routers(group.router, common.router, entry.router, manager.router, reports.router)
        scheduler = asyncio.create_task(daily_loop(bot))
        try:
            await dp.start_polling(bot)
        finally:
            scheduler.cancel()
