from django import views
from django.urls import path
from .views import (
    admin_customer_bulk_action, home, register, login_view, logout_view,
    cart_view, checkout, add_to_cart, update_cart_item, remove_from_cart,
    create_order, order_list, order_detail, product_detail,
    add_review,
    seller_dashboard, seller_product_list, seller_product_add,
    withdraw_funds,
    confirm_order_delivery,
    toggle_favorite, favorites_list,
    seller_product_edit, seller_product_delete,
    seller_product_bulk_action,
    export_sales_csv,
    admin_dashboard,
    admin_review_list, admin_review_delete, admin_review_bulk_action,
    admin_favorite_list, admin_favorite_bulk_action,
    admin_seller_management,
    admin_customer_list,
    admin_payment_list,
    export_payments_csv,
    approve_seller,
    reject_seller,
    admin_log_viewer,
    api_product_detail,
    api_seller_new_orders_count,
    admin_category_list, admin_category_add, admin_category_edit, admin_category_delete,
    admin_product_list, admin_product_add, admin_product_edit, admin_product_toggle_availability, admin_product_delete, admin_product_bulk_action, admin_seller_delete,
    admin_brand_list, admin_brand_add, admin_brand_edit, admin_brand_delete, admin_brand_bulk_action,
    admin_seller_bulk_action, admin_category_bulk_action, admin_order_bulk_action, admin_payment_bulk_action,
    api_admin_bulk_summary, 
    admin_reset_password,
    terms_of_use,
    privacy_policy,
    wishlist_bulk_remove,
)

urlpatterns = [
    path('', home, name='home'),
    path('register/', register, name='register'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),

    path('terms_of_use/', terms_of_use, name='terms_of_use'),
    path('privacy_policy/', privacy_policy, name='privacy_policy'),

    path('cart/', cart_view, name='cart'),
    path('checkout/', checkout, name='checkout'),
    path('add-to-cart/<int:product_id>/', add_to_cart, name='add_to_cart'),
    path('cart/update/<int:item_id>/', update_cart_item, name='update_cart_item'),
    path('cart/remove/<int:item_id>/', remove_from_cart, name='remove_from_cart'),

    path('orders/create/', create_order, name='create_order'),
    path('orders/', order_list, name='order_list'),
    path('orders/<str:display_id>/', order_detail, name='order_detail'),
    path('orders/<str:display_id>/confirm-delivery/', confirm_order_delivery, name='confirm_order_delivery'),

    path('favorites/', favorites_list, name='favorites_list'),
    path('favorites/toggle/<int:product_id>/', toggle_favorite, name='toggle_favorite'),

    path('product/<uuid:uuid>/', product_detail, name='product_detail'),
    path('product/<int:product_id>/review/', add_review, name='add_review'),
    path('api/product/<uuid:uuid>/', api_product_detail, name='api_product_detail'),

    # Seller Routes
    path('seller/dashboard/', seller_dashboard, name='seller_dashboard'),
    path('seller/withdraw/', withdraw_funds, name='withdraw_funds'),
    path('seller/products/', seller_product_list, name='seller_product_list'),
    path('seller/products/add/', seller_product_add, name='seller_product_add'),
    path('seller/products/edit/<uuid:uuid>/', seller_product_edit, name='seller_product_edit'),
    path('seller/products/delete/<uuid:uuid>/', seller_product_delete, name='seller_product_delete'),
    path('seller/products/bulk-action/', seller_product_bulk_action, name='seller_product_bulk_action'),
    path('seller/export-sales/', export_sales_csv, name='export_sales_csv'),
    path('seller/api/new-orders-count/', api_seller_new_orders_count, name='api_seller_new_orders_count'),

    # Admin Panel
    path('admin-panel/dashboard/', admin_dashboard, name='admin_dashboard'),
    path('admin-panel/sellers/', admin_seller_management, name='admin_seller_management'),
    path('admin-panel/reviews/', admin_review_list, name='admin_review_list'),
    path('admin-panel/reviews/delete/<int:pk>/', admin_review_delete, name='admin_review_delete'),
    path('admin-panel/reviews/bulk-action/', admin_review_bulk_action, name='admin_review_bulk_action'),
    path('admin-panel/favorites/', admin_favorite_list, name='admin_favorite_list'),
    path('admin-panel/favorites/bulk-action/', admin_favorite_bulk_action, name='admin_favorite_bulk_action'),

    path('admin-panel/sellers/bulk-action/', admin_seller_bulk_action, name='admin_seller_bulk_action'),
    path('admin-panel/sellers/delete/<int:user_id>/', admin_seller_delete, name='admin_seller_delete'),
    path('admin-panel/sellers/approve/<int:user_id>/', approve_seller, name='approve_seller'),
    path('admin-panel/sellers/reject/<int:user_id>/', reject_seller, name='reject_seller'),
    path('admin-panel/customers/', admin_customer_list, name='admin_customer_list'),
    path('admin-panel/customers/bulk-action/', admin_customer_bulk_action, name='admin_customer_bulk_action'),
    path('admin-panel/payments/', admin_payment_list, name='admin_payment_list'),
    path('admin-panel/payments/export/', export_payments_csv, name='export_payments_csv'),
    path('admin-panel/logs/', admin_log_viewer, name='admin_log_viewer'),

    # Admin - Category & Product Management
    path('admin-panel/categories/', admin_category_list, name='admin_category_list'),
    path('admin-panel/categories/add/', admin_category_add, name='admin_category_add'),
    path('admin-panel/categories/edit/<int:pk>/', admin_category_edit, name='admin_category_edit'),
    path('admin-panel/categories/delete/<int:pk>/', admin_category_delete, name='admin_category_delete'),
    path('admin-panel/categories/bulk-action/', admin_category_bulk_action, name='admin_category_bulk_action'),

    path('admin-panel/products/', admin_product_list, name='admin_product_list'),
    path('admin-panel/products/add/', admin_product_add, name='admin_product_add'),
    path('admin-panel/products/edit/<uuid:uuid>/', admin_product_edit, name='admin_product_edit'),
    path('admin-panel/products/toggle/<uuid:uuid>/', admin_product_toggle_availability, name='admin_product_toggle'),
    path('admin-panel/products/delete/<uuid:uuid>/', admin_product_delete, name='admin_product_delete'),
    path('admin-panel/products/bulk-action/', admin_product_bulk_action, name='admin_product_bulk_action'),

    path('admin-panel/brands/', admin_brand_list, name='admin_brand_list'),
    path('admin-panel/brands/add/', admin_brand_add, name='admin_brand_add'),
    path('admin-panel/brands/edit/<int:pk>/', admin_brand_edit, name='admin_brand_edit'),
    path('admin-panel/brands/delete/<int:pk>/', admin_brand_delete, name='admin_brand_delete'),
    path('admin-panel/brands/bulk-action/', admin_brand_bulk_action, name='admin_brand_bulk_action'),

    path('admin-panel/orders/bulk-action/', admin_order_bulk_action, name='admin_order_bulk_action'),
    path('admin-panel/payments/bulk-action/', admin_payment_bulk_action, name='admin_payment_bulk_action'),
    path('admin-panel/api/bulk-summary/', api_admin_bulk_summary, name='api_admin_bulk_summary'),
    path('wishlist/bulk-remove/', wishlist_bulk_remove, name='wishlist_bulk_remove'),

    # 'admin/' prefiksini 'admin-panel/' edip üýtgetdik:
    path('admin-panel/users/<int:user_id>/reset-password/', admin_reset_password, name='admin_reset_password'), 
]