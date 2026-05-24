from django.contrib import admin
from .models import (
    Category, Brand, Product, ProductImage, User,
    Cart, CartItem, Order, OrderItem, Payment
)

admin.site.site_header = 'Alkyş dolandyryş merkezi'
admin.site.site_title = 'Alkyş'

admin.site.register(Category)
admin.site.register(Brand)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    max_num = 3


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductImageInline]
    list_display = ['category', 'name', 'created', 'uploaded', 'price', 'seller']


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['fullname', 'email', 'role', 'is_active']
    list_filter = ['role', 'is_active']
    search_fields = ['fullname', 'email']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['customer', 'created_at']


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['cart', 'product', 'quantity', 'added_at']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['customer', 'status', 'created_at', 'order_id']
    list_filter = ['status', 'created_at']


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product', 'quantity', 'seller_name']  # replaced 'seller' with a method
    # Removed list_filter because 'seller' is gone; you can filter by product__seller if needed
    search_fields = ['order__order_id', 'product__name']

    def seller_name(self, obj):
        return obj.product.seller.fullname
    seller_name.short_description = 'Seller'
    seller_name.admin_order_field = 'product__seller__fullname'


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['image', 'product']
    list_filter = ['product']
    search_fields = ['product__name']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['order', 'status', 'amount']        # renamed payment_method → status
    list_filter = ['status', 'paid_at']                 # added status filtering