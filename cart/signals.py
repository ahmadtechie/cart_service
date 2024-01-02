# Signal receivers to update total_quantity when CartItem is saved or deleted
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from cart.models import CartItem


@receiver(post_save, sender=CartItem)
@receiver(post_delete, sender=CartItem)
def update_cart_total_quantity(sender, instance, **kwargs):
    print('SIGNAL TRIGGERED')
    instance.cart.save()