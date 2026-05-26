from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    Category, Brand, Product, ProductImage, User,
    Cart, CartItem, Order, OrderItem, Payment,
    Review, Favorite   # <-- Täze goşuldy
)

admin.site.site_header = 'Alkyş dolandyryş merkezi'
admin.site.site_title = 'Alkyş'


# ------------------------------------------------------------
#   KÖMEKÇI INLINE'LAR
# ------------------------------------------------------------
class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    max_num = 5   # Islege görä köpeldip bolýar


# ------------------------------------------------------------
#   REGISTRASIÝALAR
# ------------------------------------------------------------
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [ProductImageInline]
    list_display = ['name', 'category', 'price', 'discount_price', 'available', 'seller', 'created']
    list_filter = ['available', 'category', 'brand', 'seller']
    search_fields = ['name', 'description']
    raw_id_fields = ['seller']   # köp ulanyjyly saytlarda has amatly


# ------------------------------------------------------------
#   USER ADMIN – HAS BERKIDILEN
# ------------------------------------------------------------
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Bu meýdanlar esasy maglumat sahypasynda görkeziler
    list_display = ['email', 'fullname', 'role', 'is_active', 'is_approved', 'is_staff']
    list_filter = ['role', 'is_active', 'is_approved', 'is_staff', 'is_superuser']
    search_fields = ['email', 'fullname']
    ordering = ['email']

    # Mysaly: jikme-jik sahypa üçin bölümler
    fieldsets = (
        (None, {'fields': ('email', 'fullname', 'password')}),
        ('Rol we ygtyýarlyklar', {
            'fields': ('role', 'is_active', 'is_approved', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Resminamalar', {
            'fields': ('verification_document',),
            'classes': ('collapse',)   # bu bölümi bukup goýýar
        }),
    )
    # Täze ulanyjy goşulanda görkezilýän meýdanlar
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'fullname', 'password1', 'password2', 'role', 'is_approved', 'is_staff'),
        }),
    )
    # Raw ID meýdanlar köp sanly baglanyşykda peýdaly
    filter_horizontal = ['groups', 'user_permissions']


# ------------------------------------------------------------
#   SEBET WE ZAKAZ
# ------------------------------------------------------------
@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['customer', 'created_at', 'total_price']
    readonly_fields = ['total_price']


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['cart', 'product', 'quantity', 'added_at']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['display_id', 'customer', 'status', 'total_price', 'created_at']
    list_filter = ['status', 'created_at', 'funds_released']
    readonly_fields = ['display_id', 'order_id', 'total_price']


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product', 'quantity', 'price', 'line_total', 'seller_name']
    list_filter = ['order__status', 'product__seller']   # Süzgüçleri goşduk
    search_fields = ['order__display_id', 'product__name']

    def seller_name(self, obj):
        return obj.product.seller.fullname
    seller_name.short_description = 'Satyjy'
    seller_name.admin_order_field = 'product__seller__fullname'


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['order', 'amount', 'status', 'paid_at']
    list_filter = ['status', 'paid_at']


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['image', 'product']


# ------------------------------------------------------------
#   TÄZE GOŞULAN MODELLER
# ------------------------------------------------------------
@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'rating', 'created_at']
    list_filter = ['rating', 'created_at']
    search_fields = ['product__name', 'user__fullname']


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'created_at']
    search_fields = ['user__fullname', 'product__name']