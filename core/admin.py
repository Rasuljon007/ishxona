from django import forms
from django.contrib import admin

from core import services
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
from core.reports import money


@admin.register(WorkerType)
class WorkerTypeAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "manager", "member_count", "telegram_chat_id"]
    autocomplete_fields = ["manager"]

    @admin.display(description="ishchilar soni")
    def member_count(self, obj):
        return obj.members.filter(is_active=True).count()


class EmployeeForm(forms.ModelForm):
    site_password = forms.CharField(
        label="sayt paroli",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Faqat boshqaruvchi uchun. Sardor /sardor/ sahifasiga telefon raqami va shu parol bilan "
        "kiradi va faqat o'z guruhini ko'radi. Bo'sh qoldirsangiz, parol o'zgarmaydi.",
    )

    class Meta:
        model = Employee
        exclude = ["user"]

    def clean(self):
        data = super().clean()
        if data.get("site_password"):
            if data.get("role") != Employee.Role.MANAGER:
                self.add_error("site_password", "Sayt hisobi faqat boshqaruvchilar uchun.")
            elif len(data["site_password"]) < 6:
                self.add_error("site_password", "Parol kamida 6 belgi bo'lishi kerak.")
        return data


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    form = EmployeeForm
    list_display = ["full_name", "phone", "role", "worker_type", "team", "is_active", "has_telegram", "has_site"]
    list_filter = ["is_active", "role", "worker_type", "team"]
    list_editable = ["is_active"]
    search_fields = ["full_name", "phone"]
    readonly_fields = ["telegram_id", "created_at"]

    @admin.display(boolean=True, description="sayt")
    def has_site(self, obj):
        return obj.user_id is not None

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        password = form.cleaned_data.get("site_password")
        if password:
            try:
                services.set_site_password(obj, password)
            except services.ServiceError as err:
                self.message_user(request, str(err), level="error")

    @admin.display(boolean=True, description="Telegram")
    def has_telegram(self, obj):
        return obj.telegram_id is not None


class OperationInline(admin.TabularInline):
    model = Operation
    extra = 3
    fields = ["name", "worker_type", "price", "is_active"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "price_display", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    inlines = [OperationInline]
    readonly_fields = ["price_display"]

    @admin.display(description="tikish narxi (1 dona)")
    def price_display(self, obj):
        return money(obj.sewing_price) if obj.pk else "-"


@admin.register(Operation)
class OperationAdmin(admin.ModelAdmin):
    list_display = ["product", "name", "worker_type", "price", "is_active"]
    list_filter = ["product", "worker_type", "is_active"]
    search_fields = ["name", "product__name"]


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ["operation", "old_price", "new_price", "changed_at"]
    list_filter = ["operation__product"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class EntryEditInline(admin.TabularInline):
    model = EntryEdit
    extra = 0
    can_delete = False
    readonly_fields = ["editor", "field", "old_value", "new_value", "comment", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(WorkEntry)
class WorkEntryAdmin(admin.ModelAdmin):
    list_display = [
        "date",
        "worker",
        "operation",
        "quantity",
        "defect_quantity",
        "unit_price",
        "amount_display",
        "status",
        "entered_by",
        "approved_by",
    ]
    list_filter = ["status", "date", "worker__team", "operation__product"]
    search_fields = ["worker__full_name", "operation__name"]
    date_hierarchy = "date"
    readonly_fields = [
        "date",
        "worker",
        "operation",
        "quantity",
        "defect_quantity",
        "unit_price",
        "status",
        "entered_by",
        "approved_by",
        "approved_at",
        "reject_reason",
    ]
    inlines = [EntryEditInline]

    @admin.display(description="summa")
    def amount_display(self, obj):
        return money(obj.amount)

    def has_add_permission(self, request):
        # Entries are created through the bot so the one-per-day and approval rules apply.
        return False


@admin.register(EntryEdit)
class EntryEditAdmin(admin.ModelAdmin):
    list_display = ["created_at", "editor", "entry", "field", "old_value", "new_value", "comment"]
    list_filter = ["editor", "field"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
