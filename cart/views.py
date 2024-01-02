import os
import json
import logging
import redis
import requests
from django.core.serializers.json import DjangoJSONEncoder

from rest_framework import generics
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .pagination import DefaultPagination
from .serializers import CartSerializer, RetrieveCartSerializer, CartItemSerializer, \
    CartItemQuantityUpdateSerializer, CustomItemOptionsSerializer, WishlistSerializer
from .models import Cart, CartItem, ItemOption, Wishlist
from .utils import get_or_create_auth_cart, set_guest_cart_id, \
    delete_cart_from_redis, delete_cart_item_from_redis, get_cart_from_redis

redis_client = redis.StrictRedis(
    host=os.getenv('REDIS_HOST', 'localhost'),
    port=os.getenv('REDIS_PORT', 6379),
    db=0)

logger = logging.getLogger(__name__)


def get_all_carts_from_redis():
    cart_keys = redis_client.keys('cart:user:*')
    cart_keys.extend(redis_client.keys('cart:main:*'))
    logger.info(f"Cart Keys {cart_keys} retrieved successfully")
    carts = []
    for cart_key in cart_keys:
        cart_data_json = redis_client.get(cart_key)
        if cart_data_json:
            cart_data = json.loads(cart_data_json.decode('utf-8'))
            carts.append(cart_data)
    return carts


def get_all_cart_items_from_redis():
    cart_item_keys = redis_client.keys('cart_item:main:*')
    logger.info(f"Cart Keys {cart_item_keys} retrieved successfully")
    cart_items = []
    for cart_item_key in cart_item_keys:
        cart_item_data_json = redis_client.get(cart_item_key)
        if cart_item_data_json:
            cart_data = json.loads(cart_item_data_json.decode('utf-8'))
            cart_items.append(cart_data)
    return cart_items


def get_all_options_from_redis():
    item_option_keys = redis_client.keys('item_option:main:*')
    logger.info(f"Option Keys {item_option_keys} retrieved successfully")
    item_options = []
    for item_key in item_option_keys:
        option_data_json = redis_client.get(item_key)
        if option_data_json:
            option_data = json.loads(option_data_json.decode('utf-8'))
            item_options.append(option_data)
    return item_options


class MergeGuestAndAuthCartsView(GenericAPIView):
    def post(self, request, user_id, guest_cart_id=''):
        auth_cart = get_or_create_auth_cart(user_id)

        if guest_cart_id:
            guest_cart_data = redis_client.get(f'cart:main:{guest_cart_id}')
            if guest_cart_data:
                guest_cart = json.loads(guest_cart_data.decode('utf-8'))
                guest_cart_items = guest_cart.get('cart_items', [])

                if auth_cart:
                    for guest_cart_item in guest_cart_items:
                        existing_item = None
                        for auth_cart_item in auth_cart['cart_items']:
                            if (
                                    guest_cart_item['prod_id'] == auth_cart_item['prod_id']
                                    and guest_cart_item['item_options'] == auth_cart_item['item_options']
                            ):
                                existing_item = auth_cart_item
                                break

                        if existing_item:
                            existing_item['quantity'] += guest_cart_item['quantity']
                        else:
                            auth_cart['cart_items'].append(guest_cart_item)
                else:
                    auth_cart['user_id'] = user_id
                    set_guest_cart_id('')

                redis_client.delete(f'cart:main:{guest_cart_id}')

                # Update the authenticated cart in Redis
                redis_client.set(f'cart:user:{user_id}', json.dumps(auth_cart))

        return Response(auth_cart, status=status.HTTP_200_OK)


class CreateUserCartView(generics.CreateAPIView):
    """
    API View for creating user cart.

    This view creates a cart for a user which could have many cart items.
    """
    serializer_class = CartSerializer
    queryset = Cart.objects.all()

    def perform_create(self, serializer):
        print('serializer ', serializer.validated_data)
        cart = serializer.save()
        if not serializer.validated_data['user_id']:
            self.request.session['guest_cart_id'] = cart.id


class WishlistView(ModelViewSet):
    serializer_class = WishlistSerializer
    queryset = Wishlist.objects.all()
    pagination_class = DefaultPagination


class ListOptionsView(generics.ListAPIView):
    """
    API View for listing all available carts for the benefit of the admin.

    This view displays all carts.
    """
    serializer_class = CustomItemOptionsSerializer
    queryset = ItemOption.objects.all()

    def list(self, request, *args, **kwargs):
        options = get_all_options_from_redis()  # Fetch all carts from Redis

        if not options:
            logger.warning("Options retrieved from DB NOT from Redis")
            options = self.get_queryset()  # If not found in Redis, fetch from the database

        serializer = self.get_serializer(options, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ListCartView(generics.ListAPIView):
    """
    API View for listing all available carts for the benefit of the admin.

    This view displays all carts.
    """
    serializer_class = RetrieveCartSerializer
    pagination_class = DefaultPagination
    queryset = Cart.objects.all()

    def list(self, request, *args, **kwargs):
        carts = get_all_carts_from_redis()  # Fetch all carts from Redis

        if not carts:
            print('Carts retrieved from DB NOT from Redis')
            logger.warning("Carts retrieved from DB NOT from Redis")
            carts = self.get_queryset()  # If not found in Redis, fetch from the database

            serializer = self.get_serializer(carts, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(carts, status=status.HTTP_200_OK)


class RetrieveDeleteCartView(generics.RetrieveDestroyAPIView):
    serializer_class = RetrieveCartSerializer
    queryset = Cart.objects.all()

    def get_serializer_class(self):
        if self.request.method == 'GET':
            logger.info("Method in 'GET' accessed from CartItemView")
            return RetrieveCartSerializer
        return CartSerializer

    def retrieve(self, request, *args, **kwargs):
        cart_id = self.kwargs['pk']
        cart_data = self.get_user_id_from_redis(cart_id)

        if cart_data:
            cart = self.get_user_id_from_redis(cart_id)['cart']  # Fetch cart data from Redis
            print('Redis Cart Retrieval ', cart)
        else:
            logger.warning(f"Cart with ID {self.kwargs['pk']} not found in Redis, checking DB")
            cart = self.get_object()  # If not found in Redis, fetch from the database

        serializer = self.get_serializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        cart_id = self.kwargs['pk']
        cart_data = self.get_user_id_from_redis(cart_id)  # Fetch cart data from Redis

        if cart_data:
            delete_cart_from_redis(cart_data['cart']['id'], cart_data['cart']['user_id'])
        else:
            logger.warning(f"Cart with ID {self.kwargs['pk']} not found in Redis, checking DB")
            cart = self.get_object()  # If not found in Redis, fetch from the database
            self.perform_destroy(cart)  # Perform delete operation

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_user_id_from_redis(self, cart_id):
        cart_data_json = redis_client.get(f'cart:main:{cart_id}')
        if cart_data_json:
            cart_data = json.loads(cart_data_json.decode('utf-8'))
            return {
                'user_id': cart_data.get('user_id'),
                'cart': cart_data,
            }
        return None


class RetrieveUserCartView(generics.RetrieveAPIView):
    """
    API View for retrieving cart based user ID.

    This View allows you to retrieve and update details of individual order items.
    """
    serializer_class = RetrieveCartSerializer
    queryset = Cart.objects.all()
    lookup_field = 'user_id'

    def retrieve(self, request, *args, **kwargs):
        cart_data_json = redis_client.get(f"cart:user:{self.kwargs['user_id']}")

        if cart_data_json:
            cart = json.loads(cart_data_json.decode('utf-8'))
        else:
            logger.warning(f"Cart with ID {self.kwargs['user_id']} not found in Redis, checking DB")
            cart = self.get_object()  # If not found in Redis, fetch from the database

        serializer = self.get_serializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AddCartItemView(generics.CreateAPIView):
    """
    API View for adding cart item to cart.

    This View creates adds new item to an existing cart.
    """
    serializer_class = CartItemSerializer
    queryset = CartItem.objects.all()

    def get_serializer_context(self):
        return {'cart_id': self.kwargs['pk']}


class RetrieveUpdateDestroyCartItemView(generics.RetrieveUpdateDestroyAPIView):
    """
    API View for retrieving, updating, and deleting a cart item.

    This View creates retrieves, updates and deletes a cart item.
    """
    queryset = CartItem.objects.all()

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            logger.info("Method in ['PUT', 'PATCH'] accessed from CartItemView")
            return CartItemQuantityUpdateSerializer
        return CartItemSerializer

    def retrieve(self, request, *args, **kwargs):
        cart_item_data = self.get_cart_item_from_redis(self.kwargs['cart_id'], self.kwargs['pk'])

        if not cart_item_data:
            logger.warning(f'Cart with ID {self.kwargs['pk']} not found in Redis, checking DB')
            print(f"Cart with ID {self.kwargs['pk']} not found in Redis, checking DB")
            cart_item_data = self.get_object()  # If not found in Redis, fetch from the database

        serializer = self.get_serializer(cart_item_data)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        # Get the cart item to update
        cart_item_data = self.get_cart_item_from_redis(kwargs['cart_id'], kwargs['pk'])
        cart_data = get_cart_from_redis(kwargs['cart_id'])

        if not cart_item_data:
            logger.warning(f"Cart Item with ID {kwargs["pk"]} not found in Redis, checking DB")
            cart_item_data = self.get_object()  # If not found in Redis, fetch from the database

        # Update the cart item with the new data
        serializer = self.get_serializer(data=request.data, partial=True)

        if serializer.is_valid():
            # Serialize the data to JSON before saving to Redis
            serialized_data = serializer.data

            # Redis keys
            redis_cart_item_key = f'cart_item:main:{kwargs["pk"]}'
            redis_cart_other_key = f'cart_item:cart:{kwargs["cart_id"]}:{kwargs["pk"]}'
            redis_user_key = f'cart:user:{cart_data["user_id"]}' if cart_data["user_id"] else None
            redis_cart_key = f'cart:main:{cart_data["id"]}'

            cart_item_data['quantity'] = serialized_data['quantity']
            # effect the change in the db
            try:
                db_item = CartItem.objects.get(id=cart_item_data['id'])
                db_item.quantity = serialized_data['quantity']
                db_item.save()
            except CartItem.DoesNotExist:
                pass

            # update the cart itself in Redis
            if cart_data:
                for index, item in enumerate(cart_data['cart_items']):
                    if item['id'] == cart_item_data['id']:
                        # Replace the existing item with the updated item
                        cart_data['cart_items'][index] = cart_item_data
                        break
                cart_data["total_quantity"] = Cart.objects.get(id=cart_data['id']).total_quantity

            print("serialized_data['quantity']: ", serialized_data['quantity'])

            # Save the serialized data to Redis
            if redis_user_key:
                redis_client.set(redis_user_key, json.dumps(cart_data, cls=DjangoJSONEncoder))
            redis_client.set(redis_cart_key, json.dumps(cart_data, cls=DjangoJSONEncoder))
            redis_client.set(redis_cart_other_key, json.dumps(cart_item_data))
            redis_client.set(redis_cart_item_key, json.dumps(cart_item_data))

            logger.info(f"Cart with ID {kwargs['pk']} saved to Redis successfully")

            return Response(cart_item_data, status=status.HTTP_200_OK)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, *args, **kwargs):
        cart_id = self.kwargs['cart_id']
        cart_item_id = self.kwargs['pk']

        cart_item_data = self.get_cart_item_from_redis(cart_id, cart_item_id)

        if cart_item_data:
            delete_cart_item_from_redis(cart_item_id, cart_id)
        else:
            logger.warning(f"Cart Item with ID {self.kwargs['pk']} not found in Redis, checking DB")
            cart = self.get_object()  # If not found in Redis, fetch from the database
            self.perform_destroy(cart)  # Perform delete operation

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_cart_item_from_redis(self, cart_id, cart_item_id):
        cart_item_data_other_json = redis_client.get(f'cart_item:cart:{cart_id}:{cart_item_id}')
        cart_item_data_json = redis_client.get(f'cart_item:main:{cart_item_id}')

        if cart_item_data_json:
            cart_item_data = json.loads(cart_item_data_json.decode('utf-8'))
        elif cart_item_data_other_json:
            cart_item_data = json.loads(cart_item_data_other_json.decode('utf-8'))
        else:
            return None
        return cart_item_data


class CartCheckoutView(generics.CreateAPIView):
    def create(self, request, *args, **kwargs):
        # Retrieve cart items and user information from the request
        cart_items = request.data.get('cart_items', [])
        user_id = request.data.get('user_id')

        # Step 2: Check product availability and pricing (interact with Product Service)
        product_ids = [item['product_id'] for item in cart_items]

        # Step 3: Calculate the total price based on product prices and quantities

        # Step 4: Process the payment (interact with Payment Service)
        # payment_result = PaymentService.process_payment(user_id, total_price)

        # Step 5: If payment is successful, create an order (interact with Order Service)

        # If any step fails, handle the error accordingly
        return Response({'message': 'Checkout failed'}, status=status.HTTP_400_BAD_REQUEST)
