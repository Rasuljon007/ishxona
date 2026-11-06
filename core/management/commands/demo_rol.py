from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.commands.seed_demo import DEMO_PHONE_PREFIX
from core.models import Employee
from core.services import normalize_phone

ROLES = {"boshliq": Employee.Role.BOSS, "sardor": Employee.Role.MANAGER, "ishchi": Employee.Role.WORKER}


class Command(BaseCommand):
    help = (
        "Sizning Telegram hisobingizni demo xodimga bog'laydi, shunda botni boshliq, sardor yoki "
        "ishchi sifatida sinab ko'rasiz. Avval botga /start yuborib, telefon raqamingizni jo'nating."
    )

    def add_arguments(self, parser):
        parser.add_argument("rol", choices=ROLES)
        parser.add_argument("--telefon", help="Botga yuborgan raqamingiz (bir nechta bo'lsa).")
        parser.add_argument("--kim", help="Demo xodim ismining bir qismi (masalan, Gulnora).")

    def handle(self, *args, **options):
        demo = Employee.objects.filter(phone__startswith=DEMO_PHONE_PREFIX)
        if not demo.exists():
            raise CommandError("Demo ma'lumotlar yo'q. Avval: python manage.py seed_demo")
        telegram_id = self.telegram_id(options["telefon"])

        target = demo.filter(role=ROLES[options["rol"]], is_active=True).order_by("pk")
        if options["kim"]:
            target = target.filter(full_name__icontains=options["kim"])
        target = target.first()
        if not target:
            raise CommandError("Bunday demo xodim topilmadi.")

        with transaction.atomic():
            Employee.objects.filter(telegram_id=telegram_id).update(telegram_id=None)
            target.telegram_id = telegram_id
            target.save(update_fields=["telegram_id"])
        team = f", guruh: {target.team}" if target.team_id else ""
        self.stdout.write(
            self.style.SUCCESS(f"Endi botda siz: {target.full_name} ({target.get_role_display()}{team}).")
        )
        self.stdout.write("Botga /start yuboring, menyu yangilanadi.")

    def telegram_id(self, phone):
        if phone:
            employee = Employee.objects.filter(phone=normalize_phone(phone)).first()
            if not employee or not employee.telegram_id:
                raise CommandError("Bu raqam botda ro'yxatdan o'tmagan. Botga /start yuborib, raqamingizni jo'nating.")
            return employee.telegram_id
        # Your own record is the one outside the demo set; once linked, it may be a demo employee.
        own = Employee.objects.filter(telegram_id__isnull=False).exclude(phone__startswith=DEMO_PHONE_PREFIX)
        linked = Employee.objects.filter(telegram_id__isnull=False, phone__startswith=DEMO_PHONE_PREFIX)
        ids = set(own.values_list("telegram_id", flat=True)) | set(linked.values_list("telegram_id", flat=True))
        if not ids:
            raise CommandError("Botda hech kim ro'yxatdan o'tmagan. Botga /start yuborib, raqamingizni jo'nating.")
        if len(ids) > 1:
            raise CommandError("Botda bir nechta hisob bor. Raqamingizni --telefon bilan bering.")
        return ids.pop()
