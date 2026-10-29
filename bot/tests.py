import datetime as dt

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from bot import texts
from bot.handlers.reports import parse_range
from bot.scheduler import next_run


class BotTests(SimpleTestCase):
    def test_handlers_import(self):
        from bot.handlers import common, entry, group, manager, reports  # noqa: F401

    def test_plain_texts_transliterate(self):
        for key, value in texts.TEXTS.items():
            if "{" not in value:
                self.assertTrue(texts.t(key, "cyrillic"))

    def test_menu_texts_cover_both_scripts(self):
        menu = texts.menu_texts()
        self.assertIn("Oyligim", menu)
        self.assertIn("Ойлигим", menu)

    def test_values_are_escaped(self):
        self.assertEqual(texts.t("welcome", name="<x>"), "Xush kelibsiz, &lt;x&gt;! Kerakli bo'limni tanlang.")

    def test_boss_menu_has_manager_buttons(self):
        from bot.keyboards import main_menu
        from core.models import Employee

        boss = Employee(full_name="B", phone="998900000000", role=Employee.Role.BOSS)
        labels = {b.text for row in main_menu(boss).keyboard for b in row}
        for key in ("btn_pending", "btn_enter_for", "btn_edit", "btn_team_today", "btn_rep_month"):
            self.assertIn(texts.t(key), labels)

    def test_parse_range(self):
        self.assertEqual(parse_range("01.10.2026 28.10.2026"), (dt.date(2026, 10, 1), dt.date(2026, 10, 28)))
        self.assertEqual(parse_range("28.10.2026 - 01.10.2026"), (dt.date(2026, 10, 1), dt.date(2026, 10, 28)))
        self.assertIsNone(parse_range("bugun"))
        self.assertIsNone(parse_range("31.02.2026 01.03.2026"))

    @override_settings(REMINDER_HOUR=18, DAY_CLOSE_HOUR=21)
    def test_next_run(self):
        def local(day, hour, minute=0):
            return timezone.make_aware(dt.datetime(2026, 10, day, hour, minute))

        self.assertEqual(next_run(local(28, 10)), (local(28, 18), "reminders"))
        self.assertEqual(next_run(local(28, 19)), (local(28, 21), "reports"))
        self.assertEqual(next_run(local(28, 21)), (local(29, 18), "reminders"))
