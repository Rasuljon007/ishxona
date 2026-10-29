import random
import secrets
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Employee,
    EntryEdit,
    Operation,
    PriceHistory,
    Product,
    Team,
    WorkEntry,
    WorkerType,
)
from core.services import set_site_password, today

# Demo employees get phones with this prefix, so they are easy to find and remove.
DEMO_PHONE_PREFIX = "99800"

WORKER_TYPES = ["Bichuvchi", "Tikuvchi", "Overlokchi", "Dazmolchi", "Qadoqlovchi"]

# product -> [(operation, worker type, price)]
PRODUCTS = {
    "Futbolka": [
        ("Bichish", "Bichuvchi", 300),
        ("Yelka tikish", "Tikuvchi", 400),
        ("Yeng qo'yish", "Tikuvchi", 600),
        ("Yoqa qo'yish", "Tikuvchi", 700),
        ("Yon choklar", "Overlokchi", 500),
        ("Etak bukish", "Overlokchi", 400),
        ("Dazmollash", "Dazmolchi", 300),
        ("Qadoqlash", "Qadoqlovchi", 200),
    ],
    "Shim": [
        ("Bichish", "Bichuvchi", 500),
        ("Cho'ntak tikish", "Tikuvchi", 900),
        ("Zamok qo'yish", "Tikuvchi", 800),
        ("Kamar tikish", "Tikuvchi", 700),
        ("Ichki choklar", "Overlokchi", 600),
        ("Dazmollash", "Dazmolchi", 400),
        ("Qadoqlash", "Qadoqlovchi", 250),
    ],
    "Ko'ylak": [
        ("Bichish", "Bichuvchi", 600),
        ("Yoqa tikish", "Tikuvchi", 1200),
        ("Manjet tikish", "Tikuvchi", 900),
        ("Tugma qadash", "Tikuvchi", 500),
        ("Yon choklar", "Overlokchi", 600),
        ("Dazmollash", "Dazmolchi", 500),
        ("Qadoqlash", "Qadoqlovchi", 300),
    ],
    "Bolalar xalati": [
        ("Bichish", "Bichuvchi", 400),
        ("Kapyushon tikish", "Tikuvchi", 1000),
        ("Kamar tikish", "Tikuvchi", 400),
        ("Choklar", "Overlokchi", 700),
        ("Dazmollash", "Dazmolchi", 300),
        ("Qadoqlash", "Qadoqlovchi", 250),
    ],
}

# Ko'ylak goes out of production half way through the demo period.
RETIRED_PRODUCT = "Ko'ylak"

TEAMS = [
    ("Tikuvchilar-1", "Dilshod Rahimov", ["Tikuvchi"] * 6 + ["Overlokchi"] * 2),
    ("Tikuvchilar-2", "Gulnora Yusupova", ["Tikuvchi"] * 5 + ["Overlokchi"] * 2),
    ("Bichuv va pardoz", "Sherzod Karimov", ["Bichuvchi"] * 3 + ["Dazmolchi"] * 3 + ["Qadoqlovchi"] * 2),
]

FIRST_NAMES = [
    "Malika", "Nodira", "Zuhra", "Feruza", "Dilnoza", "Madina", "Shahnoza", "Mohira", "Sevara",
    "Kamola", "Umida", "Nilufar", "Barno", "Gulchehra", "Mavluda", "Ozoda", "Lola", "Hilola",
    "Aziz", "Jasur", "Bekzod", "Sardor", "Otabek", "Ulug'bek", "Rustam", "Farrux",
]
LAST_NAMES = [
    "Aliyeva", "Karimova", "Tursunova", "Qodirova", "Ismoilova", "Ergasheva", "Nazarova",
    "Sobirova", "Hasanova", "Mirzayeva", "Abdullayeva", "Xolmatova",
]

EDIT_COMMENTS = [
    "Ishchi noto'g'ri son kiritgan, qayta sanaldi",
    "Partiya qayta tekshirildi",
    "Sardor bilan kelishildi",
]
REJECT_REASONS = [
    "Bu kun bu partiya bilan ishlamagan",
    "Son ikki marta kiritilgan",
    "Boshqa qism tanlangan",
]


def male(name):
    return name in {"Aziz", "Jasur", "Bekzod", "Sardor", "Otabek", "Ulug'bek", "Rustam", "Farrux"}


def surname(first, last):
    return last[:-1] if male(first) else last


class Command(BaseCommand):
    help = (
        "Demo ma'lumotlar yaratadi: ishchi turlari, guruhlar, xodimlar, mahsulotlar va oxirgi "
        "ikki oylik ish yozuvlari. Telegram'ga hech narsa yubormaydi."
    )

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=61, help="Necha kunlik ish (standart 61).")
        parser.add_argument(
            "--reset", action="store_true", help="Avvalgi demo ma'lumotlarni o'chirib, qaytadan yaratadi."
        )
        parser.add_argument("--seed", type=int, default=2026, help="Tasodifiy sonlar uchun urug'.")

    def handle(self, *args, **options):
        demo = Employee.objects.filter(phone__startswith=DEMO_PHONE_PREFIX)
        if demo.exists():
            if not options["reset"]:
                raise CommandError("Demo ma'lumotlar allaqachon bor. Qaytadan yaratish uchun --reset bering.")
            self.remove_demo()
        self.rng = random.Random(options["seed"])
        with transaction.atomic():
            self.create(options["days"])

    def remove_demo(self):
        with transaction.atomic():
            demo = Employee.objects.filter(phone__startswith=DEMO_PHONE_PREFIX)
            get_user_model().objects.filter(employee__in=demo).delete()
            WorkEntry.objects.filter(worker__in=demo).delete()
            Team.objects.filter(name__in=[t[0] for t in TEAMS]).delete()
            demo.delete()
            Product.objects.filter(name__in=PRODUCTS).delete()
        self.stdout.write("Avvalgi demo ma'lumotlar o'chirildi.")

    def phone(self):
        self.phone_counter += 1
        return f"{DEMO_PHONE_PREFIX}{self.phone_counter:07d}"

    def create(self, days):
        rng = self.rng
        self.phone_counter = 0
        self.logins = []
        end = today()
        start = end - timedelta(days=days - 1)
        tz = timezone.get_current_timezone()

        def at(day, hour, minute=0):
            return timezone.make_aware(datetime.combine(day, time(hour, minute)), tz)

        types = {name: WorkerType.objects.get_or_create(name=name)[0] for name in WORKER_TYPES}

        products = {}
        for pname, ops in PRODUCTS.items():
            product = Product.objects.create(name=pname)
            for oname, tname, price in ops:
                Operation.objects.create(product=product, worker_type=types[tname], name=oname, price=price)
            products[pname] = product

        boss = Employee.objects.create(
            full_name="Akmal Nabiyev", phone=self.phone(), role=Employee.Role.BOSS
        )

        names = [(f, l) for f in FIRST_NAMES for l in LAST_NAMES]
        rng.shuffle(names)
        workers = []
        teams = []
        for tname, manager_name, worker_types in TEAMS:
            manager = Employee.objects.create(
                full_name=manager_name, phone=self.phone(), role=Employee.Role.MANAGER
            )
            team = Team.objects.create(name=tname, manager=manager)
            manager.team = team
            manager.save()
            teams.append(team)
            password = secrets.token_urlsafe(6)
            set_site_password(manager, password)
            self.logins.append((manager, team, password))
            for wt in worker_types:
                first, last = names.pop()
                workers.append(
                    Employee.objects.create(
                        full_name=f"{surname(first, last)} {first}",
                        phone=self.phone(),
                        role=Employee.Role.WORKER,
                        worker_type=types[wt],
                        team=team,
                        script=rng.choice([Employee.Script.LATIN] * 4 + [Employee.Script.CYRILLIC]),
                    )
                )
        # Two people who registered through the bot and are waiting to be activated.
        for _ in range(2):
            first, last = names.pop()
            Employee.objects.create(
                full_name=f"{surname(first, last)} {first}",
                phone=self.phone(),
                role=Employee.Role.WORKER,
                is_active=False,
            )
        # Everyone has been working since the start of the period.
        Employee.objects.filter(phone__startswith=DEMO_PHONE_PREFIX).update(created_at=at(start, 9))

        # Each worker's daily output depends on the person and the operation.
        skill = {w.pk: rng.uniform(0.75, 1.25) for w in workers}
        retire_day = start + timedelta(days=days // 2)
        # Price raises a few weeks in: (product, operation, new price, day).
        raises = [
            ("Futbolka", "Yoqa qo'yish", 800, start + timedelta(days=20)),
            ("Shim", "Zamok qo'yish", 900, start + timedelta(days=35)),
        ]
        current_price = {op.pk: op.price for op in Operation.objects.filter(product__in=products.values())}
        raise_by_op = {}
        for pname, oname, new_price, day in raises:
            if day > end:
                continue
            op = Operation.objects.get(product=products[pname], name=oname)
            raise_by_op[op.pk] = (new_price, day)

        ops_by_type = {}
        for op in Operation.objects.filter(product__in=products.values()).select_related("product"):
            ops_by_type.setdefault(op.worker_type_id, []).append(op)

        entries = []
        day = start
        while day <= end:
            if day.weekday() == 6:  # Sunday off
                day += timedelta(days=1)
                continue
            is_today = day == end
            for w in workers:
                if rng.random() < 0.06:  # absent
                    continue
                if is_today and rng.random() < 0.3:  # has not entered today's work yet
                    continue
                available = [
                    op for op in ops_by_type[w.worker_type_id]
                    if not (op.product.name == RETIRED_PRODUCT and day >= retire_day)
                ]
                for op in rng.sample(available, k=min(len(available), rng.choice([1, 1, 2, 2, 3]))):
                    price = current_price[op.pk]
                    if op.pk in raise_by_op and day >= raise_by_op[op.pk][1]:
                        price = raise_by_op[op.pk][0]
                    base = 60000 / price  # roughly 60 000 so'm worth of this operation per day
                    quantity = max(5, int(base * skill[w.pk] * rng.uniform(0.5, 0.9)))
                    defect = 0
                    if rng.random() < 0.12:
                        defect = rng.randint(1, max(1, quantity // 15))
                    entry = WorkEntry(
                        date=day,
                        worker=w,
                        operation=op,
                        quantity=quantity,
                        defect_quantity=defect,
                        unit_price=price,
                        entered_by=w,
                    )
                    manager = w.team.manager
                    if rng.random() < 0.1:
                        entry.entered_by = manager
                    if is_today:
                        if rng.random() < 0.4:
                            entry.status = WorkEntry.Status.APPROVED
                            entry.approved_by = manager
                            entry.approved_at = timezone.now()
                    elif rng.random() < 0.03:
                        entry.status = WorkEntry.Status.REJECTED
                        entry.approved_by = manager
                        entry.reject_reason = rng.choice(REJECT_REASONS)
                    else:
                        entry.status = WorkEntry.Status.APPROVED
                        entry.approved_by = manager if rng.random() < 0.9 else boss
                        entry.approved_at = at(day, rng.randint(17, 20), rng.randint(0, 59))
                    entries.append(entry)
            day += timedelta(days=1)
        WorkEntry.objects.bulk_create(entries, batch_size=500)

        # Apply the price raises so the catalogue and the price history match the entries.
        for op_pk, (new_price, raise_day) in raise_by_op.items():
            op = Operation.objects.get(pk=op_pk)
            op.price = new_price
            op.save()
            PriceHistory.objects.filter(operation=op).update(changed_at=at(raise_day, 8, 30))
        Product.objects.filter(name=RETIRED_PRODUCT).update(is_active=False)

        # Corrections made by managers before the day closed.
        approved = list(
            WorkEntry.objects.filter(worker__in=workers, status=WorkEntry.Status.APPROVED).select_related(
                "worker__team__manager"
            )
        )
        for entry in rng.sample(approved, k=min(len(approved), 40)):
            field = rng.choice([EntryEdit.Field.QUANTITY, EntryEdit.Field.QUANTITY, EntryEdit.Field.DEFECT])
            old = getattr(entry, field)
            if field == EntryEdit.Field.QUANTITY:
                new = max(1, old + rng.choice([-10, -5, -3, 3, 5, 10]))
            else:
                new = min(entry.quantity, old + rng.randint(1, 3))
            setattr(entry, field, new)
            entry.save(update_fields=[field, "updated_at"])
            edit = EntryEdit.objects.create(
                entry=entry,
                editor=entry.worker.team.manager,
                field=field,
                old_value=old,
                new_value=new,
                comment=rng.choice(EDIT_COMMENTS),
            )
            EntryEdit.objects.filter(pk=edit.pk).update(
                created_at=at(entry.date, rng.randint(18, 20), rng.randint(0, 59))
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo tayyor: {len(types)} ishchi turi, {len(products)} mahsulot, {len(teams)} guruh, "
                f"{len(workers)} ishchi, {len(entries)} ish yozuvi ({start} – {end})."
            )
        )
        self.stdout.write("Sardorlar sayt uchun (/sardor/): telefon raqami va parol")
        for manager, team, password in self.logins:
            self.stdout.write(f"  {team}: {manager.full_name}  {manager.phone}  {password}")
