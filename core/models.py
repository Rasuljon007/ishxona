from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum


class WorkerType(models.Model):
    name = models.CharField("nomi", max_length=100, unique=True)

    class Meta:
        verbose_name = "ishchi turi"
        verbose_name_plural = "ishchi turlari"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Employee(models.Model):
    class Role(models.TextChoices):
        BOSS = "boss", "Boshliq"
        MANAGER = "manager", "Boshqaruvchi"
        WORKER = "worker", "Ishchi"

    class Script(models.TextChoices):
        LATIN = "latin", "Lotin"
        CYRILLIC = "cyrillic", "Kirill"

    full_name = models.CharField("F.I.Sh.", max_length=150)
    phone = models.CharField(
        "telefon", max_length=20, unique=True, help_text="998901234567 ko'rinishida"
    )
    telegram_id = models.BigIntegerField("Telegram ID", unique=True, null=True, blank=True)
    role = models.CharField("rol", max_length=10, choices=Role.choices, default=Role.WORKER)
    worker_type = models.ForeignKey(
        WorkerType, verbose_name="ishchi turi", null=True, blank=True, on_delete=models.SET_NULL
    )
    team = models.ForeignKey(
        "Team",
        verbose_name="guruh",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
    )
    script = models.CharField(
        "yozuv", max_length=10, choices=Script.choices, default=Script.LATIN
    )
    is_active = models.BooleanField(
        "faol", default=True, help_text="Bot orqali o'zi ro'yxatdan o'tganlar boshliq faollashtirguncha nofaol turadi"
    )
    created_at = models.DateTimeField("qo'shilgan", auto_now_add=True)

    class Meta:
        verbose_name = "xodim"
        verbose_name_plural = "xodimlar"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    def clean(self):
        # Normalize before the uniqueness check, so "90 123 45 67" and
        # "+998901234567" are recognised as the same number.
        from core.services import normalize_phone

        self.phone = normalize_phone(self.phone)
        if not (len(self.phone) == 12 and self.phone.startswith("998")):
            raise ValidationError({"phone": "Telefon raqam 998901234567 ko'rinishida bo'lishi kerak."})

    def save(self, *args, **kwargs):
        from core.services import normalize_phone

        self.phone = normalize_phone(self.phone)
        super().save(*args, **kwargs)

    @property
    def is_boss(self):
        return self.role == self.Role.BOSS

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER


class Team(models.Model):
    name = models.CharField("nomi", max_length=100, unique=True)
    manager = models.ForeignKey(
        Employee,
        verbose_name="boshqaruvchi (sardor)",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_teams",
        limit_choices_to={"role": Employee.Role.MANAGER},
    )
    telegram_chat_id = models.BigIntegerField(
        "Telegram guruh ID",
        null=True,
        blank=True,
        help_text="Guruhda botga /ulash buyrug'ini yuborsangiz, o'zi to'ldiriladi",
    )

    class Meta:
        verbose_name = "guruh"
        verbose_name_plural = "guruhlar"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField("nomi", max_length=100, unique=True)
    is_active = models.BooleanField("faol", default=True)

    class Meta:
        verbose_name = "mahsulot"
        verbose_name_plural = "mahsulotlar"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def sewing_price(self):
        """Price of making one item: the sum of its active operations."""
        return self.operations.filter(is_active=True).aggregate(s=Sum("price"))["s"] or 0


class Operation(models.Model):
    product = models.ForeignKey(
        Product, verbose_name="mahsulot", on_delete=models.CASCADE, related_name="operations"
    )
    worker_type = models.ForeignKey(
        WorkerType, verbose_name="ishchi turi", on_delete=models.PROTECT, related_name="operations"
    )
    name = models.CharField("qism nomi", max_length=150)
    price = models.PositiveIntegerField("narxi (so'm, 1 dona)")
    is_active = models.BooleanField("faol", default=True)

    class Meta:
        verbose_name = "qism (operatsiya)"
        verbose_name_plural = "qismlar (operatsiyalar)"
        ordering = ["product__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["product", "name"], name="unique_operation_per_product")
        ]

    def __str__(self):
        return f"{self.product.name} / {self.name}"

    def save(self, *args, **kwargs):
        old_price = None
        if self.pk:
            old_price = Operation.objects.filter(pk=self.pk).values_list("price", flat=True).first()
        super().save(*args, **kwargs)
        if old_price is not None and old_price != self.price:
            PriceHistory.objects.create(operation=self, old_price=old_price, new_price=self.price)


class PriceHistory(models.Model):
    operation = models.ForeignKey(
        Operation, verbose_name="qism", on_delete=models.CASCADE, related_name="price_history"
    )
    old_price = models.PositiveIntegerField("eski narx")
    new_price = models.PositiveIntegerField("yangi narx")
    changed_at = models.DateTimeField("o'zgargan vaqt", auto_now_add=True)

    class Meta:
        verbose_name = "narx o'zgarishi"
        verbose_name_plural = "narx tarixi"
        ordering = ["-changed_at"]


class WorkEntry(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        APPROVED = "approved", "Tasdiqlangan"
        REJECTED = "rejected", "Rad etilgan"

    date = models.DateField("sana")
    worker = models.ForeignKey(
        Employee, verbose_name="ishchi", on_delete=models.PROTECT, related_name="entries"
    )
    operation = models.ForeignKey(
        Operation, verbose_name="qism", on_delete=models.PROTECT, related_name="entries"
    )
    quantity = models.PositiveIntegerField("soni")
    defect_quantity = models.PositiveIntegerField("brak", default=0)
    unit_price = models.PositiveIntegerField(
        "narx (kiritilgan kundagi)", help_text="Narx keyin o'zgarsa ham eski yozuvlar o'zgarmaydi"
    )
    status = models.CharField("holat", max_length=10, choices=Status.choices, default=Status.PENDING)
    entered_by = models.ForeignKey(
        Employee, verbose_name="kim kiritdi", on_delete=models.PROTECT, related_name="+"
    )
    approved_by = models.ForeignKey(
        Employee,
        verbose_name="kim tasdiqladi",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    approved_at = models.DateTimeField("tasdiqlangan vaqt", null=True, blank=True)
    reject_reason = models.TextField("rad etish sababi", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ish yozuvi"
        verbose_name_plural = "ish yozuvlari"
        ordering = ["-date", "worker__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "operation", "date"], name="one_entry_per_worker_operation_day"
            )
        ]

    def __str__(self):
        return f"{self.date} {self.worker} {self.operation}: {self.quantity}"

    @property
    def net_quantity(self):
        return max(self.quantity - self.defect_quantity, 0)

    @property
    def amount(self):
        return self.net_quantity * self.unit_price


class EntryEdit(models.Model):
    class Field(models.TextChoices):
        QUANTITY = "quantity", "Soni"
        DEFECT = "defect_quantity", "Brak"

    entry = models.ForeignKey(
        WorkEntry, verbose_name="yozuv", on_delete=models.CASCADE, related_name="edits"
    )
    editor = models.ForeignKey(
        Employee, verbose_name="kim o'zgartirdi", on_delete=models.PROTECT, related_name="+"
    )
    field = models.CharField("maydon", max_length=20, choices=Field.choices)
    old_value = models.PositiveIntegerField("eski qiymat")
    new_value = models.PositiveIntegerField("yangi qiymat")
    comment = models.TextField("izoh")
    created_at = models.DateTimeField("vaqt", auto_now_add=True)

    class Meta:
        verbose_name = "tahrir"
        verbose_name_plural = "tahrirlar jurnali"
        ordering = ["-created_at"]
