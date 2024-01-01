from django.contrib import admin
from .models import Cart, CartItem, ItemOption


class CartModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id', 'created_at',)
    filter_horizontal = ()
    list_filter = ()
    fieldsets = ()
    ordering = ('-created_at',)


class CartItemModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'cart', 'prod_id', 'item_options', 'quantity', 'is_active', 'created_at',)
    filter_horizontal = ()
    list_filter = ()
    fieldsets = ()
    ordering = ('-created_at',)

    def item_options(self, obj):
        # obj is the Author instance
        return ', '.join([f'({option.attribute}, {option.value})' for option in obj.item_options.all()])

    item_options.short_description = 'Options'


class ItemOptionModelAdmin(admin.ModelAdmin):
    list_display = ('id', 'cart_item', 'attribute', 'value', 'created_at', 'modified_at')
    filter_horizontal = ()
    list_filter = ()
    fieldsets = ()
    ordering = ('-created_at',)


admin.site.register(Cart, CartModelAdmin)
admin.site.register(CartItem, CartItemModelAdmin)
admin.site.register(ItemOption, ItemOptionModelAdmin)