from django import forms
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.widgets import UnfoldAdminPasswordWidget

from core import orders, services
from core.models import (
    Employee,
    EntryEdit,
    Operation,
    Order,
    PriceHistory,
    Product,
    Team,
    WorkEntry,
    WorkerType,
)
from core.reports import money

# The boss works with Xodimlar only; site logins are made from the employee page
# ("sayt paroli"), so Django's own Users and Groups pages are hidden. Accounts stay.
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(WorkerType)
class WorkerTypeAdmin(ModelAdmin):
    search_fields = ["name"]


@admin.register(Team)
class TeamAdmin(ModelAdmin):
    list_display = ["name", "manager", "member_count", "telegram_chat_id"]
    autocomplete_fields = ["manager"]

    @admin.display(description="ishchilar soni")
    def member_count(self, obj):
        return obj.members.filter(is_active=True).count()


class EmployeeForm(forms.ModelForm):
    site_password = forms.CharField(
        label="sayt paroli",
        required=False,
        widget=UnfoldAdminPasswordWidget(render_value=False),
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
class EmployeeAdmin(ModelAdmin):
    form = EmployeeForm
    list_display = ["full_name", "phone", "role_label", "worker_type", "team", "is_active", "has_telegram", "has_site"]
    list_filter = ["is_active", "role", "worker_type", "team"]
    list_editable = ["is_active"]
    search_fields = ["full_name", "phone"]
    readonly_fields = ["telegram_id", "created_at"]

    @display(
        description="rol",
        ordering="role",
        label={
            Employee.Role.BOSS.label: "danger",
            Employee.Role.MANAGER.label: "info",
            Employee.Role.WORKER.label: "success",
        },
    )
    def role_label(self, obj):
        return obj.get_role_display()

    @admin.display(boolean=True, description="sayt")
    def has_site(self, obj):
        return obj.user_id is not None

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.user_id and obj.user.username != obj.phone:
            try:
                services.sync_site_username(obj)
            except services.ServiceError as err:
                self.message_user(request, str(err), level="error")
        password = form.cleaned_data.get("site_password")
        if password:
            try:
                services.set_site_password(obj, password)
            except services.ServiceError as err:
                self.message_user(request, str(err), level="error")

    @admin.display(boolean=True, description="Telegram")
    def has_telegram(self, obj):
        return obj.telegram_id is not None


class OperationInline(TabularInline):
    model = Operation
    extra = 3
    fields = ["name", "worker_type", "price", "is_active"]


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ["name", "operation_count", "price_display", "is_active", "edit_link"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    inlines = [OperationInline]
    readonly_fields = ["price_display"]

    @admin.display(description="tikish narxi (1 dona)")
    def price_display(self, obj):
        return money(obj.sewing_price) if obj.pk else "-"

    @admin.display(description="qismlar soni")
    def operation_count(self, obj):
        return obj.operations.filter(is_active=True).count()

    @admin.display(description="")
    def edit_link(self, obj):
        # The product name is a link but does not look like one, so the boss could not
        # find how to change an existing product. This button makes it obvious.
        return format_html(
            '<a href="{}" style="display:inline-flex;align-items:center;gap:4px;padding:4px 12px;'
            "border-radius:999px;font-weight:600;font-size:13px;white-space:nowrap;"
            'background:var(--color-primary-600);color:#fff">'
            '<span class="material-symbols-outlined" style="font-size:16px">edit</span>Tahrirlash</a>',
            reverse("admin:core_product_change", args=[obj.pk]),
        )


@admin.register(Operation)
class OperationAdmin(ModelAdmin):
    list_display = ["product", "name", "worker_type", "price", "is_active"]
    list_display_links = ["product", "name"]
    # Prices can be changed right in the list; each change still lands in Narx tarixi.
    list_editable = ["price", "is_active"]
    list_filter = ["product", "worker_type", "is_active"]
    search_fields = ["name", "product__name"]


@admin.register(PriceHistory)
class PriceHistoryAdmin(ModelAdmin):
    list_display = ["operation", "old_price", "new_price", "changed_at"]
    list_filter = ["operation__product"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class EntryEditInline(TabularInline):
    model = EntryEdit
    extra = 0
    can_delete = False
    readonly_fields = ["editor", "field", "old_value", "new_value", "comment", "created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ["title", "client", "progress_bar", "deadline_display", "status_label", "start_date"]
    list_filter = ["status", "product"]
    search_fields = ["client", "product__name", "note"]
    autocomplete_fields = ["product"]
    readonly_fields = ["progress_panel"]
    fieldsets = [
        (None, {"fields": ["product", "quantity", "client", "start_date", "deadline", "status", "note"]}),
        ("Bajarilishi", {"fields": ["progress_panel"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("product")

    def get_fieldsets(self, request, obj=None):
        # A new order has no progress yet.
        return self.fieldsets if obj else self.fieldsets[:1]

    @admin.display(description="zakaz", ordering="pk")
    def title(self, obj):
        return f"#{obj.pk} · {obj.quantity} {obj.product.name}"

    @admin.display(description="bajarilishi")
    def progress_bar(self, obj):
        return render_to_string("core/orders/bar.html", {"p": orders.progress(obj)})

    @admin.display(description="muddat", ordering="deadline")
    def deadline_display(self, obj):
        if not obj.deadline:
            return "-"
        state = orders.progress(obj).deadline_state
        colour = {"late": "#dc2626", "soon": "#d97706"}.get(state)
        text = obj.deadline.strftime("%d.%m.%Y")
        if colour:
            return format_html('<b style="color:{}">{}</b>', colour, text)
        return text

    @display(
        description="holat",
        ordering="status",
        label={
            Order.Status.NEW.label: "info",
            Order.Status.IN_PROGRESS.label: "warning",
            Order.Status.DONE.label: "success",
            Order.Status.DELIVERED.label: "success",
            Order.Status.CANCELLED.label: "danger",
        },
    )
    def status_label(self, obj):
        return obj.get_status_display()

    @admin.display(description="")
    def progress_panel(self, obj):
        if not obj.pk:
            return "-"
        return render_to_string("core/orders/progress.html", {"p": orders.progress(obj)})


@admin.register(WorkEntry)
class WorkEntryAdmin(ModelAdmin):
    list_display = [
        "date_short",
        "worker",
        "operation",
        "order",
        "quantity",
        "defect_quantity",
        "unit_price",
        "amount_display",
        "status_label",
        "entered_by",
        "approved_by",
    ]
    list_filter = ["status", "date", "worker__team", "operation__product", "order"]
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

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # The boss may move an entry to another order of the same product.
        if db_field.name == "order":
            entry_id = request.resolver_match.kwargs.get("object_id") if request.resolver_match else None
            entry = WorkEntry.objects.filter(pk=entry_id).select_related("operation").first()
            if entry:
                kwargs["queryset"] = Order.objects.filter(product_id=entry.operation.product_id).select_related(
                    "product"
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="sana", ordering="date")
    def date_short(self, obj):
        return obj.date.strftime("%d.%m.%Y")

    @admin.display(description="summa")
    def amount_display(self, obj):
        return money(obj.amount)

    @display(
        description="holat",
        ordering="status",
        label={
            WorkEntry.Status.PENDING.label: "warning",
            WorkEntry.Status.APPROVED.label: "success",
            WorkEntry.Status.REJECTED.label: "danger",
        },
    )
    def status_label(self, obj):
        return obj.get_status_display()

    def has_add_permission(self, request):
        # Entries are created through the bot so the one-per-day and approval rules apply.
        return False


@admin.register(EntryEdit)
class EntryEditAdmin(ModelAdmin):
    list_display = ["created_at", "editor", "entry", "field", "old_value", "new_value", "comment"]
    list_filter = ["editor", "field"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
