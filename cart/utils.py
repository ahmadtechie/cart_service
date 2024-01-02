import datetime
import os
import logging
import json

import redis
from django.conf import settings

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse

from cart.models import CartItem, Cart

redis_client = redis.StrictRedis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=os.getenv('REDIS_PORT', 6379),
    db=0)

logger = logging.getLogger(__name__)


def get_guest_cart_id(request):
    # guest_cart_id = request.COOKIES['guest_cart_id']
    print('request.COOKIES ', request.COOKIES)
    return None


def set_guest_cart_id(cart_id: str):
    response = HttpResponse("Setting cart ID in a cookie")
    response.set_cookie('guest_cart_id', cart_id, path='/')
    return response


def get_or_create_auth_cart(user_id: int):
    redis_key = f'cart:user:{user_id}'
    auth_cart_data = redis_client.get(redis_key)
    print("auth_cart_data", json.loads(auth_cart_data.decode('utf-8')))

    if auth_cart_data:
        return json.loads(auth_cart_data.decode('utf-8'))

    # If the cart doesn't exist in Redis, create a new cart
    auth_cart = {
        'user_id': user_id,
        'cart_items': []
    }

    # Updated Redis key for the authenticated user's cart
    redis_key = f'cart:user:{user_id}'
    redis_client.set(redis_key, json.dumps(auth_cart))
    return auth_cart


def compare_dicts(ordered_dicts, array_of_dicts):
    for od in ordered_dicts:
        found = False
        for ad in array_of_dicts:
            if od['attribute'] == ad['attribute'] and od['value'] == ad['value']:
                found = True
                break
        if not found:
            return False
    return True


def get_existing_cart_item_redis(cart, prod_id, options_data, user_id=None):
    # Construct the Redis key based on the user_id
    redis_key = f'cart:user:{user_id}' if user_id is not None else f'cart:main:{cart["id"]}'

    # Retrieve cart data from Redis
    cart_data_json = redis_client.get(redis_key)

    if cart_data_json:
        # If data is found, parse it from JSON
        cart_data = json.loads(cart_data_json.decode('utf-8'))
        logger.info(f'Cart detail: {cart_data} retrieved successfully')
        cart_items = cart_data.get('cart_items', [])

        logger.info(f'cart_items {cart_items} retrieved successfully')

        for cart_item_data in cart_items:
            logger.info(f'Cart Item: {cart_item_data}')
            if cart_item_data['prod_id'] == prod_id:
                options = cart_item_data.get('item_options', [])

                is_cart_item_exist = compare_dicts(options_data, options)

                if is_cart_item_exist:
                    logger.info(f"Cart with ID {cart_item_data['id']} matches the current cart item")
                    return cart_item_data
            else:
                continue
    return None


def merge_cart_items(cart, cart_item, quantity_to_add):
    # Update the quantity of the existing cart item
    cart_item['quantity'] += quantity_to_add

    # update the cart item count in the db too
    try:
        db_item = CartItem.objects.get(id=cart_item['id'])
        db_item.quantity += quantity_to_add
        db_item.save()
        # print('total_quantity', Cart.objects.get(id=cart['id']).total_quantity)
    except CartItem.DoesNotExist:
        pass

    logger.info(f"New CartItem quantity = {cart_item['quantity']} + {quantity_to_add}")

    # Find the index of the cart_item in the cart_items list
    for index, item in enumerate(cart['cart_items']):
        if item['id'] == cart_item['id']:
            # Replace the existing item with the updated item
            cart['cart_items'][index] = cart_item
            break
    cart["total_quantity"] = Cart.objects.get(id=cart['id']).total_quantity

    # print("cart ", cart)
    # Save the updated cart data back to Redis
    redis_user_key = f'cart:user:{cart["user_id"]}' if cart["user_id"] else None
    redis_cart_key = f'cart:main:{cart["id"]}'
    redis_cart_item_key = f'cart_item:main:{cart_item['id']}'
    redis_cart_other_key = f'cart_item:cart:{cart["id"]}:{cart_item['id']}'

    if redis_user_key:
        redis_client.set(redis_user_key, json.dumps(cart, cls=DjangoJSONEncoder))
    redis_client.set(redis_cart_key, json.dumps(cart, cls=DjangoJSONEncoder))
    redis_client.set(redis_cart_other_key, json.dumps(cart_item, cls=DjangoJSONEncoder))
    redis_client.set(redis_cart_item_key, json.dumps(cart_item, cls=DjangoJSONEncoder))
    logger.info(f"Cart with ID {cart['id']} saved to Redis successfully")


def get_cart_from_redis(cart_id=None, user_id=None):
    cart_data_json = redis_client.get(f'cart:main:{cart_id}')
    user_cart_data_json = redis_client.get(f'cart:user:{user_id}')
    # print(cart_data_json, user_cart_data_json)

    if cart_data_json:
        logger.info(f"Cart with ID {cart_id} retrieved from Redis successfully")
        return json.loads(cart_data_json.decode('utf-8'))
    elif user_cart_data_json:
        logger.info(f"Cart with User ID {user_id} retrieved from Redis successfully")
        return json.loads(user_cart_data_json.decode('utf-8'))
    return None


def delete_cart_from_redis(cart_id, user_id=None):
    if user_id:
        redis_user_key = f'cart:user:{user_id}'
        redis_client.delete(redis_user_key)
    redis_cart_key = f'cart:main:{cart_id}'
    redis_client.delete(redis_cart_key)
    logger.info(f'Cart with ID {cart_id} deleted from Redis successfully')


def delete_cart_item_from_redis(cart_item_id, cart_id=None):
    if cart_id:
        redis_client.delete(f'cart_item:cart:{cart_id}:{cart_item_id}')
    redis_client.delete(f'cart_item:main:{cart_item_id}')
    logger.info(f'Cart Item with ID {cart_item_id} deleted from Redis successfully')
