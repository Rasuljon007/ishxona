"""Orders ("zakazlar"): which open order a work entry belongs to, and how far each order is."""

import datetime as dt
from dataclasses import dataclass, field

from django.db.models import Q, Sum

from core.models import Order, WorkEntry

NOT_REJECTED = ~Q(status=WorkEntry.Status.REJECTED)


def open_orders(product_id):
    """Open orders of a product, the most urgent first (earliest deadline, then oldest)."""
    orders = Order.objects.filter(product_id=product_id, status__in=Order.OPEN_STATUSES)
    return sorted(
        orders,
        key=lambda o: (o.deadline is None, o.deadline or dt.date.max, o.start_date or dt.date.max, o.pk),
    )


def _net(qs):
    totals = qs.aggregate(q=Sum("quantity"), d=Sum("defect_quantity"))
    return max((totals["q"] or 0) - (totals["d"] or 0), 0)


def pick_order(operation):
    """The order a new entry for this operation goes to.

    The most urgent open order that still needs this part; when every open order already
    has enough of it, the most urgent one anyway. None when the product has no open order.
    """
    orders = open_orders(operation.product_id)
    for order in orders:
        made = _net(WorkEntry.objects.filter(NOT_REJECTED, order=order, operation=operation))
        if made < order.quantity:
            return order
    return orders[0] if orders else None


@dataclass
class PartProgress:
    operation: object
    done: int = 0
    pending: int = 0
    defect: int = 0
    quantity: int = 0

    @property
    def percent(self):
        return min(round(self.done * 100 / self.quantity), 100) if self.quantity else 0

    @property
    def left(self):
        return max(self.quantity - self.done, 0)


@dataclass
class WorkerRow:
    worker: object
    cells: list = field(default_factory=list)  # approved net pieces, in the order of `parts`
    total: int = 0
    pending: int = 0


@dataclass
class Progress:
    order: Order
    parts: list
    workers: list

    @property
    def done(self):
        """Finished items: an item is ready only when every part of it is sewn."""
        if not self.parts:
            return 0
        return min(min(p.done for p in self.parts), self.order.quantity)

    @property
    def percent(self):
        q = self.order.quantity
        return min(round(self.done * 100 / q), 100) if q else 0

    @property
    def left(self):
        return max(self.order.quantity - self.done, 0)

    @property
    def deadline_state(self):
        """"late", "soon" or "" — used to colour unfinished orders near their deadline."""
        order = self.order
        if not order.deadline or not order.is_open or self.done >= order.quantity:
            return ""
        from core.services import today

        days = (order.deadline - today()).days
        if days < 0:
            return "late"
        if days <= Order.WARN_DAYS:
            return "soon"
        return ""

    @property
    def days_left(self):
        if not self.order.deadline:
            return None
        from core.services import today

        return (self.order.deadline - today()).days


def progress(order):
    operations = list(order.product.operations.filter(is_active=True).order_by("pk"))
    linked_ops = WorkEntry.objects.filter(order=order).values_list("operation_id", flat=True)
    # A part switched off after work started still shows what was sewn for it.
    extra = order.product.operations.filter(is_active=False, pk__in=linked_ops).order_by("pk")
    operations += list(extra)
    parts = {op.pk: PartProgress(operation=op, quantity=order.quantity) for op in operations}
    workers = {}
    entries = (
        WorkEntry.objects.filter(NOT_REJECTED, order=order)
        .select_related("worker")
        .order_by("worker__full_name")
    )
    index = {op.pk: i for i, op in enumerate(operations)}
    for e in entries:
        part = parts.get(e.operation_id)
        if part is None:
            continue
        row = workers.get(e.worker_id)
        if row is None:
            row = workers[e.worker_id] = WorkerRow(worker=e.worker, cells=[0] * len(operations))
        if e.status == WorkEntry.Status.APPROVED:
            part.done += e.net_quantity
            part.defect += e.defect_quantity
            row.cells[index[e.operation_id]] += e.net_quantity
            row.total += e.net_quantity
        else:
            part.pending += e.quantity
            row.pending += e.quantity
    return Progress(order=order, parts=list(parts.values()), workers=list(workers.values()))


def sync_status(order):
    """Move an open order between Yangi, Jarayonda and Tayyor by its progress.

    Topshirilgan and Bekor qilingan are set by the boss and never changed here.
    """
    if order is None:
        return
    order.refresh_from_db(fields=["status"])
    if order.status not in (Order.Status.NEW, Order.Status.IN_PROGRESS, Order.Status.DONE):
        return
    p = progress(order)
    if p.parts and p.done >= order.quantity:
        status = Order.Status.DONE
    elif order.entries.filter(NOT_REJECTED).exists():
        status = Order.Status.IN_PROGRESS
    else:
        status = Order.Status.NEW
    if status != order.status:
        order.status = status
        order.save(update_fields=["status"])
