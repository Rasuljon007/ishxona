"""Keep each order's status in step with the work entries linked to it."""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from core import orders
from core.models import Order, WorkEntry


@receiver(pre_save, sender=WorkEntry)
def remember_old_order(sender, instance, **kwargs):
    instance._old_order_id = (
        WorkEntry.objects.filter(pk=instance.pk).values_list("order_id", flat=True).first()
        if instance.pk
        else None
    )


def _sync(*order_ids):
    for order in Order.objects.filter(pk__in={i for i in order_ids if i}):
        orders.sync_status(order)


@receiver(post_save, sender=WorkEntry)
def entry_saved(sender, instance, **kwargs):
    _sync(instance.order_id, getattr(instance, "_old_order_id", None))


@receiver(post_delete, sender=WorkEntry)
def entry_deleted(sender, instance, **kwargs):
    _sync(instance.order_id)
