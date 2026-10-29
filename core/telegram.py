"""Telegram messages sent from the website (the bot process sends its own through aiogram)."""

import json
import logging
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)


def send_message(chat_id, text):
    if not settings.BOT_TOKEN or not chat_id:
        return
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(request, timeout=10).close()
    except Exception as exc:  # a failed notification must not break the page
        log.warning("Could not notify %s: %s", chat_id, exc)


def tell_worker(entry, key, **extra):
    from bot.texts import t
    from bot.utils import entry_fields

    worker = entry.worker
    send_message(worker.telegram_id, t(key, worker.script, **entry_fields(entry), **extra))
