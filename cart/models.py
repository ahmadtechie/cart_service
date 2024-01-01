import os
import json
import uuid
import logging

import redis
from django.db import models
from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger(__name__)

# Create a Redis client instance
redis_client = redis.StrictRedis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=os.getenv('REDIS_PORT', 6379),
    db=0)


class CartItemManager(models.Manager):
    def get_queryset(self):
        return super(CartItemManager, self).get_queryset().filter(is_active=True)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    objects = models.Manager()

    class Meta:
        abstract = True


class Wishlist(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=50, null=True, blank=True)
    product_id = models.CharField(max_length=50, null=True, blank=True)


class Cart(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_cart_from_redis(cls, cart_id):
        cart_data = redis_client.get(cart_id)
        if cart_data:
            return Cart(**json.loads(cart_data.decode('utf-8')))
        return None

    # override to save directly to redis
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.save_cart_to_redis()

    def save_cart_to_redis(self):
        cart_data = {
            "id": str(self.id),
            "user_id": self.user_id,
            "cart_items": [],
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

        cart_items_data = []

        # Iterate through related CartItem instances
        for cart_item in self.cart_items.all():
            # Load CartItem data
            cart_item_data = {
                "id": str(cart_item.id),
                "cart_id": str(cart_item.cart_id),
                "prod_id": cart_item.prod_id,
                "quantity": cart_item.quantity,
                "is_active": cart_item.is_active,
                "created_at": cart_item.created_at,
                "modified_at": cart_item.modified_at,
            }

            item_options_data = []

            # Iterate through related ItemOption instances for the CartItem
            for item_option in cart_item.item_options.all():
                option_data = {
                    "id": str(item_option.id),
                    "cart_item_id": str(item_option.cart_item_id),
                    "attribute": item_option.attribute,
                    "value": item_option.value,
                    "created_at": item_option.created_at,
                    "modified_at": item_option.modified_at,
                }
                item_options_data.append(option_data)

            cart_item_data["item_options"] = item_options_data
            cart_items_data.append(cart_item_data)

        cart_data["cart_items"] = cart_items_data

        cart_data_json = json.dumps(cart_data, cls=DjangoJSONEncoder)
        redis_cart_key = f'cart:main:{self.id}'
        redis_user_key = f'cart:user:{self.user_id}'

        try:
            # Attempt to set the data in Redis
            redis_client.set(redis_cart_key, cart_data_json)
            redis_client.set(redis_user_key, cart_data_json)
            logging.info(f"Cart with ID 'cart:main:{self.id}' added to Redis successfully")
        except redis.exceptions.ConnectionError as e:
            logging.error(f"Error saving data to Redis: {str(e)}")
        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")

    def __str__(self):
        return str(self.id)


class CartItem(TimeStampedModel):
    id = models.AutoField(primary_key=True)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='cart_items')
    prod_id = models.CharField(max_length=100)
    quantity = models.IntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    objects = CartItemManager()

    def sub_total(self, prod_price):
        return prod_price * self.quantity

    # override to save directly to redis
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.save_cart_item_to_redis()

    # override the safe method to save the cart item to Redis
    def save_cart_item_to_redis(self, *args, **kwargs):
        cart_item_data = {
            "id": str(self.id),
            "cart_id": str(self.cart_id),
            "prod_id": self.prod_id,
            "quantity": self.quantity,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

        item_options_data = []

        # Iterate through related ItemOption instances for the CartItem
        for item_option in self.item_options.all():
            option_data = {
                "id": str(item_option.id),
                "cart_item_id": str(item_option.cart_item_id),
                "attribute": item_option.attribute,
                "value": item_option.value,
                "created_at": item_option.created_at,
                "modified_at": item_option.modified_at,
            }
            item_options_data.append(option_data)

        cart_item_data["item_options"] = item_options_data

        redis_key = f'cart_item:main:{self.id}'
        redis_cart_key = f'cart_item:cart:{self.cart_id}:{self.id}'
        cart_item_data_json = json.dumps(cart_item_data, cls=DjangoJSONEncoder)

        try:
            # Attempt to set the data in Redis
            redis_client.set(redis_key, cart_item_data_json)
            redis_client.set(redis_cart_key, cart_item_data_json)
            logging.info(f"Cart Item with ID 'cart_item:main:{self.id}' added/modified in Redis successfully")
        except redis.exceptions.ConnectionError as e:
            logging.error(f"Error saving Cart Item to Redis: {str(e)}")
        except Exception as e:
            logging.error(f"An error occurred while saving cart item to Redis: {str(e)}")

        self.cart.save_cart_to_redis()

    # override the delete method to delete the cart item from Redis
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

        # Delete cart item from Redis
        redis_key = f'cart_item:main:{self.id}'
        redis_client.delete(redis_key)
        logging.info(f"Cart Item with ID 'cart_item:main:{self.id}' deleted from Redis successfully")

        # Save cart items to cart's Redis representation after deletion
        self.cart.save_cart_to_redis()

    # get cart items from redis
    @classmethod
    def get_cart_items_from_redis(cls, cart_id):
        cart_data = redis_client.get(cart_id)
        if cart_data:
            cart_dict = json.loads(cart_data.decode('utf-8'))
            cart_items = cart_dict.get('cart_items', [])
            return [CartItem(**item) for item in cart_items]
        return []

    def __str__(self):
        return str(self.id)


class ItemOption(models.Model):
    id = models.AutoField(primary_key=True)
    cart_item = models.ForeignKey(CartItem, on_delete=models.CASCADE, related_name='item_options')
    attribute = models.CharField(max_length=60)
    value = models.CharField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.save_item_options_to_redis()

    def save_item_options_to_redis(self):
        # Serialize the item option data
        item_option_data = {
            "id": str(self.id),
            "cart_item_id": str(self.cart_item_id),
            "attribute": self.attribute,
            "value": self.value,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

        redis_key = f'item_option:main:{self.id}'
        redis_cart_item_key = f'item_option:cart_item:{self.cart_item_id}:{self.id}'
        item_option_data_json = json.dumps(item_option_data, cls=DjangoJSONEncoder)
        try:
            redis_client.set(redis_cart_item_key, item_option_data_json)
            redis_client.set(redis_key, item_option_data_json)
            logging.info(f"Item Option with ID 'item_option:main:{self.id}' added into Redis")
        except redis.exceptions.ConnectionError as e:
            logging.error(f"Error saving Item Option to Redis: {str(e)}")
        except Exception as e:
            logging.error(f"An error occurred while saving Item Option to Redis: {str(e)}")

        self.cart_item.save_cart_item_to_redis()

    def delete(self, *args, **kwargs):
        # Remove the reference from the cart item's list of item_options
        self.cart_item.item_options.remove(self)

        super().delete(*args, **kwargs)

        redis_key = f'item_option:main:{self.id}'
        redis_client.delete(redis_key)

        # Save the cart item to Redis after removing the item option
        self.cart_item.save_cart_item_to_redis()

    def __str__(self):
        return str(self.id)
