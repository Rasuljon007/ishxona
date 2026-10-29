import datetime as dt
import os

from django.test import TestCase, override_settings
from django.utils import timezone

from core import reports, services
from core.models import Employee, EntryEdit, Operation, PriceHistory, Product, Team, WorkEntry, WorkerType
from core.services import ServiceError
from core.translit import to_cyrillic


def at(hour, day=None):
    day = day or dt.date(2026, 10, 28)
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hour, 0)))


@override_settings(DAY_CLOSE_HOUR=21, MAX_QUANTITY=5000)
class ServiceTests(TestCase):
    def setUp(self):
        self.sewer = WorkerType.objects.create(name="Tikuvchi")
        self.ironer = WorkerType.objects.create(name="Dazmolchi")
        self.boss = Employee.objects.create(full_name="Boshliq", phone="901111111", role=Employee.Role.BOSS, telegram_id=1)
        self.gavhar = Employee.objects.create(
            full_name="Gavhar opa", phone="902222222", role=Employee.Role.MANAGER, telegram_id=2
        )
        self.other_manager = Employee.objects.create(
            full_name="Boshqa sardor", phone="903333333", role=Employee.Role.MANAGER, telegram_id=3
        )
        self.team = Team.objects.create(name="Tikuvchilar-1", manager=self.gavhar)
        self.team2 = Team.objects.create(name="Tikuvchilar-2", manager=self.other_manager)
        self.ali = Employee.objects.create(
            full_name="Ali", phone="904444444", worker_type=self.sewer, team=self.team, telegram_id=4
        )
        self.vali = Employee.objects.create(
            full_name="Vali", phone="905555555", worker_type=self.sewer, team=self.team2, telegram_id=5
        )
        self.shorts = Product.objects.create(name="Shortik")
        self.elastic = Operation.objects.create(product=self.shorts, worker_type=self.sewer, name="Belga rezinka", price=500)
        self.overlock = Operation.objects.create(product=self.shorts, worker_type=self.sewer, name="Overlok", price=200)
        self.iron = Operation.objects.create(product=self.shorts, worker_type=self.ironer, name="Dazmollash", price=100)

    def test_phone_is_normalized(self):
        self.assertEqual(self.ali.phone, "998904444444")
        self.assertEqual(services.normalize_phone("+998 (90) 444-44-44"), "998904444444")

    def test_product_price_is_sum_of_operations(self):
        self.assertEqual(self.shorts.sewing_price, 800)

    def test_price_change_is_recorded_and_old_entries_keep_their_price(self):
        entry = services.submit_entry(self.ali, self.elastic, 10, now=at(10))
        self.elastic.price = 600
        self.elastic.save()
        self.assertEqual(PriceHistory.objects.get().new_price, 600)
        entry.refresh_from_db()
        self.assertEqual(entry.unit_price, 500)

    def test_register_known_phone_links_telegram(self):
        Employee.objects.create(full_name="Yangi", phone="998906666666")
        employee, is_new = services.register_by_contact(77, "+998906666666", "Yangi")
        self.assertFalse(is_new)
        self.assertEqual(employee.telegram_id, 77)

    def test_register_unknown_phone_creates_inactive_worker(self):
        employee, is_new = services.register_by_contact(78, "998907777777", "Kimdir")
        self.assertTrue(is_new)
        self.assertFalse(employee.is_active)

    def test_register_rejects_phone_bound_to_another_account(self):
        with self.assertRaises(ServiceError):
            services.register_by_contact(99, "998904444444", "Ali")

    def test_worker_entry_waits_for_approval(self):
        entry = services.submit_entry(self.ali, self.elastic, 120, now=at(10))
        self.assertEqual(entry.status, WorkEntry.Status.PENDING)
        self.assertEqual(services.worker_month(self.ali, entry.date)["amount"], 0)
        services.approve(self.gavhar, entry, now=at(11))
        self.assertEqual(services.worker_month(self.ali, entry.date)["amount"], 120 * 500)

    def test_one_entry_per_operation_per_day(self):
        services.submit_entry(self.ali, self.elastic, 10, now=at(10))
        with self.assertRaises(ServiceError):
            services.submit_entry(self.ali, self.elastic, 5, now=at(12))
        # another operation the same day is fine
        services.submit_entry(self.ali, self.overlock, 5, now=at(12))
        # the same operation the next day is fine
        services.submit_entry(self.ali, self.elastic, 5, now=at(10, dt.date(2026, 10, 29)))

    def test_worker_cannot_enter_after_manager_entered(self):
        services.manager_enter(self.gavhar, self.ali, self.elastic, 50, now=at(10))
        with self.assertRaisesMessage(ServiceError, "boshqaruvchi allaqachon kiritgan"):
            services.submit_entry(self.ali, self.elastic, 50, now=at(11))

    def test_manager_cannot_duplicate_worker_entry(self):
        services.submit_entry(self.ali, self.elastic, 50, now=at(10))
        with self.assertRaises(ServiceError):
            services.manager_enter(self.gavhar, self.ali, self.elastic, 50, now=at(11))

    def test_manager_entry_is_approved_immediately(self):
        entry = services.manager_enter(self.gavhar, self.ali, self.elastic, 50, now=at(10))
        self.assertEqual(entry.status, WorkEntry.Status.APPROVED)
        self.assertEqual(entry.entered_by, self.gavhar)

    def test_rejected_entry_can_be_resubmitted(self):
        entry = services.submit_entry(self.ali, self.elastic, 500, now=at(10))
        services.reject(self.gavhar, entry, "Son noto'g'ri")
        entry = services.submit_entry(self.ali, self.elastic, 50, now=at(11))
        self.assertEqual(entry.status, WorkEntry.Status.PENDING)
        self.assertEqual(entry.quantity, 50)
        self.assertEqual(entry.reject_reason, "")

    def test_reject_requires_reason(self):
        entry = services.submit_entry(self.ali, self.elastic, 10, now=at(10))
        with self.assertRaises(ServiceError):
            services.reject(self.gavhar, entry, " ")

    def test_manager_only_handles_own_team(self):
        entry = services.submit_entry(self.vali, self.elastic, 10, now=at(10))
        with self.assertRaises(ServiceError):
            services.approve(self.gavhar, entry)
        with self.assertRaises(ServiceError):
            services.manager_enter(self.gavhar, self.vali, self.overlock, 5, now=at(10))
        self.assertEqual(services.pending_for(self.gavhar), [])
        self.assertEqual(len(services.pending_for(self.boss)), 1)
        services.approve(self.boss, entry)

    def test_operation_must_match_worker_type(self):
        with self.assertRaises(ServiceError):
            services.submit_entry(self.ali, self.iron, 10, now=at(10))

    def test_day_closes_at_close_hour(self):
        with self.assertRaises(ServiceError):
            services.submit_entry(self.ali, self.elastic, 10, now=at(21))

    def test_edit_requires_comment_and_is_logged(self):
        entry = services.manager_enter(self.gavhar, self.ali, self.elastic, 100, now=at(10))
        with self.assertRaises(ServiceError):
            services.edit_entry(self.gavhar, entry, "quantity", 90, "", now=at(12))
        entry = services.edit_entry(self.gavhar, entry, "quantity", 90, "Qayta sanaldi", now=at(12))
        self.assertEqual(entry.quantity, 90)
        edit = EntryEdit.objects.get()
        self.assertEqual((edit.old_value, edit.new_value, edit.editor), (100, 90, self.gavhar))

    def test_edit_not_allowed_after_day_closes(self):
        entry = services.manager_enter(self.gavhar, self.ali, self.elastic, 100, now=at(10))
        with self.assertRaises(ServiceError):
            services.edit_entry(self.gavhar, entry, "quantity", 90, "Kech qoldi", now=at(21))

    def test_defect_reduces_pay(self):
        entry = services.manager_enter(self.gavhar, self.ali, self.elastic, 100, now=at(10))
        entry = services.edit_entry(self.gavhar, entry, "defect_quantity", 4, "4 ta brak", now=at(12))
        self.assertEqual(entry.amount, 96 * 500)
        with self.assertRaises(ServiceError):
            services.edit_entry(self.gavhar, entry, "defect_quantity", 101, "Ko'p", now=at(12))
        with self.assertRaises(ServiceError):
            services.edit_entry(self.gavhar, entry, "quantity", 3, "Kam", now=at(12))

    def test_operations_for_hides_entered_ones(self):
        services.submit_entry(self.ali, self.elastic, 10, now=at(10))
        ops = services.operations_for(self.ali, self.shorts, dt.date(2026, 10, 28))
        self.assertEqual(ops, [self.overlock])

    def test_range_summary(self):
        services.manager_enter(self.gavhar, self.ali, self.elastic, 10, now=at(10))
        services.manager_enter(self.other_manager, self.vali, self.elastic, 20, now=at(10))
        pending = services.submit_entry(self.ali, self.overlock, 5, now=at(10))
        day = dt.date(2026, 10, 28)
        data = services.range_summary(day, day)
        self.assertEqual(data["total_amount"], 30 * 500)
        self.assertEqual(data["workers"][0].name, "Vali")
        self.assertEqual(len(data["operations"]), 1)
        services.approve(self.gavhar, pending)
        self.assertEqual(services.range_summary(day, day, team=self.team)["total_amount"], 10 * 500 + 5 * 200)

    def test_unusual_quantity(self):
        for d in range(20, 25):
            WorkEntry.objects.create(
                date=dt.date(2026, 10, d), worker=self.ali, operation=self.elastic, quantity=100,
                unit_price=500, status=WorkEntry.Status.APPROVED, entered_by=self.ali,
            )
        normal = services.submit_entry(self.ali, self.elastic, 150, now=at(10))
        self.assertFalse(services.is_unusual(normal))
        normal.quantity = 250
        self.assertTrue(services.is_unusual(normal))

    def test_bind_team_chat_permissions(self):
        services.bind_team_chat(self.gavhar, self.team.pk, -100)
        self.team.refresh_from_db()
        self.assertEqual(self.team.telegram_chat_id, -100)
        with self.assertRaises(ServiceError):
            services.bind_team_chat(self.gavhar, self.team2.pk, -200)
        with self.assertRaises(ServiceError):
            services.bind_team_chat(self.ali, self.team.pk, -300)

    def test_pdfs_are_generated(self):
        services.manager_enter(self.gavhar, self.ali, self.elastic, 10, now=at(10))
        day = dt.date(2026, 10, 28)
        team_pdf = reports.team_daily_pdf(self.team, day)
        self.assertTrue(team_pdf.startswith(b"%PDF"))
        self.assertIsNone(reports.team_daily_pdf(self.team2, day))
        self.assertTrue(reports.summary_pdf(day, day).startswith(b"%PDF"))


class TranslitTests(TestCase):
    def test_words(self):
        cases = {
            "Ishxona": "Ишхона",
            "o'zbek": "ўзбек",
            "G'alaba": "Ғалаба",
            "yo'q": "йўқ",
            "Ma'lumot": "Маълумот",
            "Choy": "Чой",
            "ertaga": "эртага",
            "Yozuv": "Ёзув",
            "tasdiqlayman": "тасдиқлайман",
            "Brak": "Брак",
        }
        for latin, cyrillic in cases.items():
            self.assertEqual(to_cyrillic(latin), cyrillic, latin)

    def test_keeps_tags_and_numbers(self):
        self.assertEqual(to_cyrillic("<b>Soni</b>: 120"), "<b>Сони</b>: 120")


class SeedDemoTests(TestCase):
    def test_creates_two_months_and_resets(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        call_command("seed_demo", days=10, stdout=open(os.devnull, "w"))
        self.assertTrue(WorkEntry.objects.filter(status=WorkEntry.Status.APPROVED).exists())
        self.assertFalse(Employee.objects.filter(telegram_id__isnull=False).exists())
        self.assertFalse(Team.objects.filter(telegram_chat_id__isnull=False).exists())
        self.assertEqual(PriceHistory.objects.count(), 0)
        start = services.today() - dt.timedelta(days=9)
        self.assertTrue(reports.summary_pdf(start, services.today()).startswith(b"%PDF"))
        with self.assertRaises(CommandError):
            call_command("seed_demo", days=10)
        call_command("seed_demo", days=61, reset=True, stdout=open(os.devnull, "w"))
        self.assertEqual(PriceHistory.objects.count(), 2)
        self.assertEqual(Employee.objects.filter(role=Employee.Role.BOSS).count(), 1)
