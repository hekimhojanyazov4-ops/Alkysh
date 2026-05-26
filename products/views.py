import csv
import os
import json
import logging
import stripe
from uuid import UUID
import uuid as uuid_pkg
from decimal import Decimal
from datetime import timedelta
from functools import wraps
from django.db.models import Q, OuterRef, Subquery, Exists, Case, When, Value, IntegerField, Avg, Sum, F, DecimalField, ProtectedError, Count
from django.shortcuts import render, redirect, get_object_or_404
from django.apps import apps
from django.conf import settings
from django.contrib import messages, admin
from django.contrib.auth import login, authenticate, logout, get_user_model
from django.core.mail import send_mail
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction, models as django_models
from django.db.models.functions import TruncDate
from django.http import JsonResponse, HttpResponse, Http404
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt

from .models import (
    Category, Brand,
    Cart,
    CartItem,
    Order,
    OrderItem,
    Product,
    ProductImage,
    Favorite,
    Payment,
    Review,
)

User = get_user_model()

from .forms import (
    CustomUserCreationForm, CategoryForm, BrandForm, AdminProductForm,
    ProductForm, ProductImageFormSet,
    CartItemUpdateForm,
    CustomAuthenticationForm,
    ReviewForm,
)

logger = logging.getLogger(__name__)

# ==================== DECORATORS ====================
def customer_required(view_func):
    return user_passes_test(
        lambda user: user.is_authenticated and user.role == User.Role.CUSTOMER,
        login_url='login',
    )(view_func)

def exclude_admins(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated:
            is_admin = request.user.is_staff or request.user.is_superuser or \
                       (hasattr(request.user, 'role') and request.user.role == User.Role.ADMIN)
            if is_admin:
                messages.warning(request, "Access Restricted: Administrative accounts must use the Admin Portal for management tasks.")
                return redirect('admin_dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# ==================== TEXT NORMALIZATION & SEARCH ====================
import unicodedata
from difflib import SequenceMatcher


def normalize_text(text):
    text = unicodedata.normalize('NFKD', str(text)).lower()
    replacements = str.maketrans({
        'ä': 'a', 'á': 'a', 'à': 'a', 'å': 'a', 'â': 'a', 'ã': 'a',
        'ö': 'o', 'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o',
        'ü': 'u', 'ú': 'u', 'ù': 'u', 'û': 'u',
        'ý': 'y', 'ÿ': 'y',
        'ş': 's', 'ç': 'c', 'ñ': 'n', 'ğ': 'g', 'ž': 'z',
        'æ': 'ae', 'œ': 'oe'
    })
    translated = text.translate(replacements)
    return ''.join(ch for ch in translated if ch.isalnum() or ch.isspace())


def is_similar_search(query, target):
    q = normalize_text(query)
    t = normalize_text(target)
    if q in t:
        return True
    words = q.split()
    if words and all(w in t for w in words):
        return True
    if SequenceMatcher(None, q, t).ratio() >= 0.60:
        return True
    return any(SequenceMatcher(None, w, t).ratio() >= 0.70 for w in words)


# ==================== HOME VIEW ====================
def home(request):
    q = request.GET.get('q', '').strip()
    category_slug = request.GET.get('category')

    if not request.user.is_authenticated:
        ads = [
            {
                'title': 'Curated Elegance',
                'subtitle': 'Discover hand‑picked luxury products from top sellers.',
                'image': 'https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?q=80&w=2070',
                'cta_text': 'Shop Collection',
                'link': '#'
            },
            {
                'title': 'Summer Collection',
                'subtitle': 'Explore our latest arrivals for the season. Fresh styles await.',
                'image': 'https://images.unsplash.com/photo-1523381210434-271e8be1f52b?q=80&w=2070',
                'cta_text': 'View Trends',
                'link': '#'
            },
            {
                'title': 'Premium Brands',
                'subtitle': 'Exclusive access to designers found nowhere else.',
                'image': 'https://images.unsplash.com/photo-1441986300917-64674bd600d8?q=80&w=2070',
                'cta_text': 'Explore Brands',
                'link': '#'
            }
        ]
        context = {
            'ads': ads,
            'categories': [],
            'products': [],
            'featured_products': [],
            'favorite_ids': [],
            'active_category': None,
        }
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return HttpResponse(status=403)
        return render(request, 'home.html', context)

    # Authenticated view
    first_image_qs = ProductImage.objects.filter(
        product__category=OuterRef('pk'),
        product__available=True
    ).order_by('product__created', 'id').values('image')[:1]

    categories = Category.objects.filter(
        Exists(Product.objects.filter(category=OuterRef('pk'), available=True))
    ).annotate(first_image_path=Subquery(first_image_qs))

    products = Product.objects.filter(available=True)\
        .select_related('category', 'brand', 'seller')\
        .prefetch_related('images')\
        .annotate(review_count=Count('reviews'))

    if request.user.role == User.Role.SELLER:
        products = products.filter(seller=request.user)

    if category_slug:
        products = products.filter(category__slug=category_slug)

    if q:
        exact_matches = products.filter(Q(name__iexact=q) | Q(description__icontains=q))
        similar_matches = products.filter(
            Q(name__icontains=q) | Q(brand__name__icontains=q) | Q(category__name__icontains=q)
        ).exclude(id__in=exact_matches)
        combined = (exact_matches | similar_matches).distinct()
        products = combined.annotate(
            relevance=Case(
                When(id__in=exact_matches.values('id'), then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        ).order_by('relevance', 'name')
    else:
        products = products.order_by('-created')

    featured_products = products.order_by('?')[:8] if products.exists() else []
    active_category = Category.objects.filter(slug=category_slug).first() if category_slug else None
    favorite_ids = list(Favorite.objects.filter(user=request.user).values_list('product_id', flat=True))

    context = {
        'categories': categories,
        'active_category': active_category,
        'products': products,
        'favorite_ids': favorite_ids,
        'featured_products': featured_products,
        'ads': [],
    }

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'product_grid.html', context)

    return render(request, 'home.html', context)


# ==================== AUTHENTICATION VIEWS ====================
def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome {user.fullname}! Your account has been created.')
            if user.role == User.Role.SELLER:
                return redirect('seller_dashboard')
            return redirect('home')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserCreationForm()
    return render(request, 'register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=email, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.fullname}!')
                next_url = request.GET.get('next', '')
                if not next_url or next_url == '/':
                    if user.role == User.Role.ADMIN: return redirect('admin_dashboard')
                    if user.role == User.Role.SELLER: return redirect('seller_dashboard')
                    return redirect('home')
                if next_url and not url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}
                ):
                    next_url = ''
                return redirect(next_url or 'home')
        else:
            messages.error(request, 'Invalid email or password.')
    else:
        form = CustomAuthenticationForm()
    return render(request, 'login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


# ==================== CART HELPERS ====================
def get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(customer=user)
    return cart


# ==================== CART VIEWS ====================
@login_required
@customer_required
def cart_view(request):
    cart = get_or_create_cart(request.user)
    items = cart.items.select_related('product', 'product__brand').all()
    return render(request, 'cart.html', {'cart': cart, 'items': items, 'form': CartItemUpdateForm()})


@login_required
@customer_required
def checkout(request):
    cart = get_or_create_cart(request.user)
    items = cart.items.select_related('product').all()
    if not items.exists():
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart')
    total = sum(item.get_cost() for item in items)
    return render(request, 'checkout.html', {'items': items, 'total': total})


@login_required
@customer_required
def update_cart_item(request, item_id):
    if request.method == 'POST':
        cart_item = get_object_or_404(CartItem, id=item_id, cart__customer=request.user)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            try:
                data = json.loads(request.body)
                quantity = int(data.get('quantity', 1))
                if quantity > 0:
                    cart_item.quantity = quantity
                    cart_item.save()
                    cart = cart_item.cart
                    return JsonResponse({
                        'success': True,
                        'line_total': str(cart_item.get_cost()),
                        'cart_total': str(sum(item.get_cost() for item in cart.items.all())),
                        'cart_count': cart.items.aggregate(total=Sum('quantity'))['total'] or 0
                    })
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'success': False, 'error': 'Invalid quantity'}, status=400)
        quantity = request.POST.get('quantity')
        if quantity and int(quantity) > 0:
            cart_item.quantity = int(quantity)
            cart_item.save()
            messages.success(request, 'Cart updated.')
    return redirect('cart')


@login_required
@customer_required
def remove_from_cart(request, item_id):
    if request.method == 'POST':
        cart_item = get_object_or_404(CartItem, id=item_id, cart__customer=request.user)
        product_name = cart_item.product.name
        cart_item.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            cart = get_or_create_cart(request.user)
            cart_count = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
            cart_total = sum(item.get_cost() for item in cart.items.all())
            return JsonResponse({
                'success': True,
                'message': f'{product_name} removed from your cart.',
                'cart_count': cart_count,
                'cart_total': str(cart_total)
            })
        messages.success(request, f'{product_name} removed from your cart.')
    return redirect('cart')


# ==================== ORDER VIEWS ====================
@login_required
@customer_required
def create_order(request):
    if request.method == 'POST':
        cart = get_or_create_cart(request.user)
        cart_items = cart.items.select_related('product').select_for_update().all()
        if not cart_items.exists():
            messages.warning(request, 'Your cart is empty.')
            return redirect('cart')

        payment_method = request.POST.get('payment_method', 'Cash on Delivery')
        try:
            with transaction.atomic():
                order = Order.objects.create(customer=request.user, payment_method=payment_method)
                line_items = []
                for cart_item in cart_items:
                    OrderItem.objects.create(
                        order=order,
                        product=cart_item.product,
                        quantity=cart_item.quantity,
                        price=cart_item.product.effective_price,
                    )
                    line_items.append({
                        'price_data': {
                            'currency': 'usd',
                            'product_data': {'name': cart_item.product.name},
                            'unit_amount': int(cart_item.product.effective_price * 100),
                        },
                        'quantity': cart_item.quantity,
                    })

                if payment_method == 'Credit/Debit Card':
                    stripe_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
                    if not stripe_key:
                        raise ValueError("Stripe configuration missing.")
                    stripe.api_key = stripe_key
                    checkout_session = stripe.checkout.Session.create(
                        payment_method_types=['card'],
                        line_items=line_items,
                        mode='payment',
                        success_url=request.build_absolute_uri(
                            reverse('order_detail', args=[order.display_id])
                        ) + '?payment=success',
                        cancel_url=request.build_absolute_uri(reverse('checkout')) + '?payment=cancelled',
                    )
                    order.stripe_session_id = checkout_session.id
                    order.save()
                    cart.items.all().delete()
                    return redirect(checkout_session.url, code=303)

                order.status = Order.Status.CONFIRMED
                order.save()
                cart.items.all().delete()
                messages.success(request, f'Order #{order.display_id} has been placed successfully!')
                return redirect('order_detail', display_id=order.display_id)

        except Exception as e:
            logger.error(f"Order creation failed: {str(e)}", exc_info=True)
            messages.error(request, "There was an issue processing your order. Please try again.")
            return redirect('checkout')
    return redirect('cart')


def paginate_queryset(request, queryset, page_size=10):
    paginator = Paginator(queryset, page_size)
    page_number = request.GET.get('page')
    try:
        return paginator.page(page_number)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


def apply_sorting(request, queryset, default_order='-id'):
    return queryset.order_by(request.GET.get('order_by', default_order))


@login_required
def order_list(request):
    q = request.GET.get('q', '').strip()
    if request.user.role == User.Role.ADMIN:
        orders = Order.objects.select_related('customer')
    elif request.user.role == User.Role.SELLER:
        orders = Order.objects.filter(items__product__seller=request.user).select_related('customer').distinct()
    elif request.user.role == User.Role.CUSTOMER:
        orders = Order.objects.filter(customer=request.user)
    else:
        return redirect('home')

    orders = orders.order_by('-created_at')
    if q:
        orders = orders.filter(
            Q(display_id__icontains=q) |
            Q(order_id__icontains=q) |
            Q(items__product__name__icontains=q) |
            Q(customer__email__icontains=q) |
            Q(customer__fullname__icontains=q)
        ).distinct()

    template = 'admin_order_list.html' if request.user.role == User.Role.ADMIN else 'order_list.html'
    return render(request, template, {'orders': orders})


@login_required
@exclude_admins
def order_detail(request, display_id):
    lookup_filter = Q(display_id=display_id)
    try:
        uuid_pkg.UUID(display_id)
        lookup_filter |= Q(order_id=display_id)
    except (ValueError, TypeError):
        pass

    if request.user.role == User.Role.ADMIN:
        order = get_object_or_404(Order, lookup_filter)
    elif request.user.role == User.Role.SELLER:
        order = get_object_or_404(Order, lookup_filter, items__product__seller=request.user)
    else:
        order = get_object_or_404(Order, lookup_filter, customer=request.user)

    items = order.items.select_related('product', 'product__brand').all()
    if request.user.role == User.Role.SELLER:
        items = items.filter(product__seller=request.user)

    return render(request, 'order_detail.html', {'order': order, 'items': items})


@login_required
def update_order_status(request, display_id):
    lookup_filter = Q(display_id=display_id)
    try:
        uuid_pkg.UUID(display_id)
        lookup_filter |= Q(order_id=display_id)
    except (ValueError, TypeError):
        pass

    if request.method != 'POST':
        return redirect('order_detail', display_id=display_id)

    new_status = request.POST.get('status')
    if new_status not in dict(Order.Status.choices).keys():
        messages.error(request, 'Invalid status.')
        return redirect('order_detail', display_id=display_id)

    if request.user.role == User.Role.ADMIN:
        order = get_object_or_404(Order, lookup_filter)
    elif request.user.role == User.Role.SELLER:
        order = get_object_or_404(Order, lookup_filter, items__product__seller=request.user)
    else:
        messages.error(request, 'You do not have permission to change order status.')
        return redirect('order_detail', display_id=display_id)

    if order.status == Order.Status.DELIVERED:
        messages.warning(request, 'Delivered orders cannot be changed.')
        return redirect('order_detail', display_id=display_id)

    order.status = new_status
    if new_status == Order.Status.DELIVERED:
        order.funds_released = True
    order.save()
    messages.success(request, f'Order #{order.display_id} status updated to {order.get_status_display()}.')
    return redirect('order_detail', display_id=order.display_id)


@csrf_exempt
def stripe_webhook(request):
    if request.method != 'POST':
        return HttpResponse(status=405)
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)
    if not webhook_secret:
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.error(f"Stripe Webhook Signature Verification Failed: {str(e)}")
        return HttpResponse(status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        session_id = session['id']
        try:
            order = Order.objects.get(stripe_session_id=session_id, status=Order.Status.PENDING)
            order.status = Order.Status.CONFIRMED
            order.save()
        except Order.DoesNotExist:
            pass

    return HttpResponse(status=200)


@login_required
@customer_required
def confirm_order_delivery(request, display_id):
    if request.method == 'POST':
        lookup_filter = Q(display_id=display_id)
        try:
            uuid_pkg.UUID(display_id)
            lookup_filter |= Q(order_id=display_id)
        except (ValueError, TypeError):
            pass

        order = get_object_or_404(Order, lookup_filter, customer=request.user)
        if order.status == Order.Status.CANCELLED:
            messages.error(request, "Cannot confirm delivery for a cancelled order.")
        elif order.status == Order.Status.DELIVERED:
            messages.info(request, "This order is already marked as delivered.")
        else:
            order.status = Order.Status.DELIVERED
            order.funds_released = True
            order.save()
            messages.success(request, f"Order #{order.display_id} confirmed. Funds have been released to the seller.")
    return redirect('order_detail', display_id=order.display_id)


@login_required
@customer_required
def toggle_favorite(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        favorite, created = Favorite.objects.get_or_create(user=request.user, product=product)
        if not created:
            favorite.delete()
            is_favorite = False
            message = f"{product.name} removed from favorites."
        else:
            is_favorite = True
            message = f"{product.name} added to favorites."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'is_favorite': is_favorite, 'message': message})
        messages.success(request, message)
        return redirect(request.META.get('HTTP_REFERER', 'home'))
    return JsonResponse({'success': False}, status=400)


@login_required
@customer_required
def favorites_list(request):
    favorites = Favorite.objects.filter(user=request.user).select_related('product', 'product__category', 'product__brand').prefetch_related('product__images')
    return render(request, 'favorites.html', {'favorites': favorites})


# ==================== PRODUCT DETAIL ====================
def product_detail(request, uuid):
    product_qs = Product.objects.select_related('category', 'brand', 'seller').prefetch_related('images')
    if request.user.is_authenticated and request.user.role == User.Role.SELLER:
        product_qs = product_qs.filter(seller=request.user)
    product = get_object_or_404(product_qs, uuid=uuid, available=True)

    Product.objects.filter(id=product.id).update(view_count=F('view_count') + 1)
    product.refresh_from_db()

    effective_price = product.discount_price or product.price
    savings = product.price - product.discount_price if product.discount_price else 0
    reviews = product.reviews.select_related('user').all()
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    review_form = ReviewForm()

    related_products = Product.objects.filter(
        category=product.category, available=True
    ).exclude(id=product.id).select_related('brand').prefetch_related('images').annotate(
        review_count=Count('reviews')
    ).order_by('-created')[:4]

    recently_viewed_uuids = request.session.get('recently_viewed', [])
    current_uuid_str = str(uuid)
    if current_uuid_str in recently_viewed_uuids:
        recently_viewed_uuids.remove(current_uuid_str)
    recently_viewed_uuids.insert(0, current_uuid_str)
    request.session['recently_viewed'] = recently_viewed_uuids[:6]
    request.session.modified = True

    viewed_ids = [uid for uid in recently_viewed_uuids[1:] if uid != current_uuid_str]
    recently_viewed = []
    if viewed_ids:
        products_map = Product.objects.filter(
            uuid__in=viewed_ids, available=True
        ).select_related('brand').prefetch_related('images').annotate(
            review_count=Count('reviews')
        ).in_bulk(field_name='uuid')
        for uid in viewed_ids:
            try:
                recently_viewed.append(products_map[UUID(uid)])
            except (KeyError, ValueError):
                continue

    is_favorite = (
        Favorite.objects.filter(user=request.user, product=product).exists()
        if request.user.is_authenticated else False
    )

    context = {
        'product': product,
        'related_products': related_products,
        'recently_viewed': recently_viewed,
        'effective_price': effective_price,
        'savings': savings,
        'is_favorite': is_favorite,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'review_form': review_form,
    }
    return render(request, 'product_detail.html', context)


@login_required
@customer_required
def add_review(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id, available=True)
        form = ReviewForm(request.POST)
        if form.is_valid():
            if Review.objects.filter(product=product, user=request.user).exists():
                messages.warning(request, "You have already reviewed this product.")
            else:
                review = form.save(commit=False)
                review.product = product
                review.user = request.user
                review.save()
                messages.success(request, 'Your review has been submitted.')
        return redirect('product_detail', uuid=product.uuid)
    return redirect('home')


@login_required
@customer_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id, available=True)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            try:
                data = json.loads(request.body)
                quantity = int(data.get('quantity', 1))
            except (json.JSONDecodeError, ValueError):
                quantity = 1
        else:
            try:
                quantity = int(request.POST.get('quantity', 1))
            except (ValueError, TypeError):
                quantity = 1
        if quantity < 1:
            quantity = 1

        cart = get_or_create_cart(request.user)
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, defaults={'quantity': quantity}
        )
        if not created:
            CartItem.objects.filter(id=cart_item.id).update(quantity=F('quantity') + quantity)

        message = f'{quantity} × {product.name} added to your cart.'
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            cart_count = cart.items.aggregate(total=Sum('quantity'))['total'] or 0
            return JsonResponse({'success': True, 'message': message, 'cart_count': cart_count, 'item_id': cart_item.id})

        messages.success(request, message)
        referer = request.META.get('HTTP_REFERER', '')
        return redirect(referer if referer else 'cart')
    return redirect('home')


def api_product_detail(request, uuid):
    product = get_object_or_404(
        Product.objects.annotate(review_count=Count('reviews')).prefetch_related('images'),
        uuid=uuid, available=True
    )
    data = {
        'name': product.name,
        'category': product.category.name,
        'price': str(product.price),
        'discount_price': str(product.discount_price) if product.discount_price else None,
        'effective_price': str(product.effective_price),
        'description': product.description,
        'images': [img.image.url for img in product.images.all()],
        'id': product.id,
        'review_count': product.review_count
    }
    return JsonResponse(data)


# ==================== SELLER VIEWS ====================
@login_required
@user_passes_test(lambda u: u.role == User.Role.SELLER, login_url='login')
def seller_dashboard(request):
    if not request.user.is_approved:
        return render(request, 'seller_dashboard.html', {'pending_approval': True})

    order_items = OrderItem.objects.filter(product__seller=request.user).select_related('order', 'product').annotate(
        item_revenue=F('quantity') * F('price')
    )
    available_revenue = order_items.filter(
        order__status=Order.Status.DELIVERED, order__funds_released=True
    ).aggregate(total=Sum('item_revenue'))['total'] or Decimal('0.00')
    escrow_revenue = order_items.filter(
        order__status__in=[Order.Status.CONFIRMED, Order.Status.PROCESSING, Order.Status.SHIPPED]
    ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or Decimal('0.00')
    total_orders = order_items.values('order').distinct().count()
    total_products = Product.objects.filter(seller=request.user).count()
    avg_order_value = available_revenue / total_orders if total_orders > 0 else Decimal('0.00')

    start_date = timezone.now().date() - timedelta(days=29)
    daily_sales = order_items.filter(order__created_at__date__gte=start_date) \
        .annotate(day=TruncDate('order__created_at')).values('day') \
        .annotate(revenue=Sum('item_revenue')).order_by('day')

    top_products = order_items.values('product__name', 'product__available') \
        .annotate(units_sold=Sum('quantity'), revenue=Sum('item_revenue')).order_by('-units_sold')[:5]

    context = {
        'total_revenue': available_revenue,
        'escrow_revenue': escrow_revenue,
        'total_orders': total_orders,
        'total_products': total_products,
        'avg_order_value': avg_order_value,
        'chart_labels': [s['day'].strftime('%b %d') for s in daily_sales],
        'chart_data': [float(s['revenue']) for s in daily_sales],
        'recent_sales': order_items.order_by('-order__created_at')[:5],
        'top_products': top_products
    }
    return render(request, 'seller_dashboard.html', context)


@login_required
@user_passes_test(lambda u: u.role == User.Role.SELLER, login_url='login')
def api_seller_new_orders_count(request):
    if not request.user.is_approved:
        return JsonResponse({'count': 0})
    count = Order.objects.filter(
        items__product__seller=request.user,
        status__in=[Order.Status.PENDING, Order.Status.CONFIRMED]
    ).distinct().count()
    return JsonResponse({'count': count})


@login_required
@user_passes_test(lambda u: u.role == User.Role.SELLER, login_url='login')
def withdraw_funds(request):
    if request.method == 'POST':
        messages.success(request, "Withdrawal request submitted successfully. It will be processed within 3-5 business days.")
    return redirect('seller_dashboard')


@login_required
@user_passes_test(lambda u: u.role == User.Role.SELLER, login_url='login')
def seller_product_list(request):
    products = Product.objects.filter(seller=request.user).select_related('category', 'brand').order_by('-created')
    q = request.GET.get('q', '').strip()
    category_id = request.GET.get('category')
    status = request.GET.get('status')
    if q: products = products.filter(Q(name__icontains=q) | Q(description__icontains=q))
    if category_id: products = products.filter(category_id=category_id)
    if status == 'active': products = products.filter(available=True)
    elif status == 'hidden': products = products.filter(available=False)

    paginator = Paginator(products, 10)
    page = request.GET.get('page')
    try:
        products = paginator.page(page)
    except PageNotAnInteger:
        products = paginator.page(1)
    except EmptyPage:
        products = paginator.page(paginator.num_pages)

    return render(request, 'seller_product_list.html', {
        'products': products,
        'categories': Category.objects.all(),
    })


@login_required
@user_passes_test(lambda u: u.role == User.Role.SELLER, login_url='login')
def seller_product_add(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        form.instance.seller = request.user
        formset = ProductImageFormSet(request.POST, request.FILES, instance=form.instance)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, 'Product added successfully.')
            return redirect('seller_product_list')
    else:
        form = ProductForm()
        formset = ProductImageFormSet()
    return render(request, 'seller_product_form.html', {
        'form': form, 'formset': formset, 'title': 'Add New Product'
    })


@login_required
@user_passes_test(lambda u: u.role == User.Role.SELLER, login_url='login')
def seller_product_edit(request, uuid):
    product = get_object_or_404(Product, uuid=uuid, seller=request.user)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        formset = ProductImageFormSet(request.POST, request.FILES, instance=product)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, 'Product updated successfully.')
            return redirect('seller_product_list')
    else:
        form = ProductForm(instance=product)
        formset = ProductImageFormSet(instance=product)
    return render(request, 'seller_product_form.html', {
        'form': form, 'formset': formset, 'title': 'Edit Product', 'product': product
    })


@login_required
@user_passes_test(lambda u: u.role == User.Role.SELLER, login_url='login')
def seller_product_delete(request, uuid):
    product = get_object_or_404(Product, uuid=uuid, seller=request.user)
    if request.method == 'POST':
        try:
            product.delete()
            messages.success(request, 'Product has been removed.')
        except ProtectedError:
            messages.error(request, f"Cannot delete '{product.name}' because it has already been ordered by customers.")
    return redirect('seller_product_list')


@login_required
@user_passes_test(lambda u: u.role == User.Role.SELLER, login_url='login')
def seller_product_bulk_action(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids')
        action = request.POST.get('action')
        if not ids:
            messages.warning(request, "No products selected.")
            return redirect('seller_product_list')
        products = Product.objects.filter(id__in=ids, seller=request.user)
        try:
            with transaction.atomic():
                if action == 'make_active':
                    count = products.update(available=True)
                    messages.success(request, f"Successfully activated {count} products.")
                elif action == 'make_hidden':
                    count = products.update(available=False)
                    messages.success(request, f"Successfully hidden {count} products.")
                elif action == 'delete':
                    deleted_count, _ = products.delete()
                    messages.success(request, f"Successfully deleted {deleted_count} products.")
        except ProtectedError:
            messages.error(request, "Some products cannot be deleted because they are linked to existing orders.")
    return redirect('seller_product_list')


@login_required
@user_passes_test(lambda u: u.role == User.Role.SELLER, login_url='login')
def export_sales_csv(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    response = HttpResponse(content_type='text/csv')
    filename = f"sales_report_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(['Order ID', 'Date', 'Product Name', 'Category', 'Quantity', 'Price', 'Total'])

    order_items = OrderItem.objects.filter(product__seller=request.user).select_related('order', 'product', 'product__category')
    if start_date:
        order_items = order_items.filter(order__created_at__date__gte=start_date)
    if end_date:
        order_items = order_items.filter(order__created_at__date__lte=end_date)

    for item in order_items:
        writer.writerow([
            item.order.order_id,
            item.order.created_at.strftime('%Y-%m-%d %H:%M'),
            item.product.name,
            item.product.category.name,
            item.quantity,
            item.price,
            item.line_total
        ])
    return response


# ==================== ADMIN VIEWS ====================
def _get_admin_registry_data():
    registry = admin.site._registry
    data = {}
    for model_cls in registry:
        app_label = model_cls._meta.app_label
        if app_label not in data:
            data[app_label] = []
        data[app_label].append({
            'model_name': model_cls._meta.model_name,
            'verbose_name': model_cls._meta.verbose_name_plural.capitalize(),
            'app_label': app_label,
        })
    return data


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_dashboard(request):
    pending_sellers_count = User.objects.filter(role=User.Role.SELLER, is_approved=False).count()
    total_revenue = OrderItem.objects.filter(
        order__status=Order.Status.DELIVERED
    ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or Decimal('0.00')
    escrow_funds = OrderItem.objects.filter(
        order__status__in=[Order.Status.CONFIRMED, Order.Status.PROCESSING, Order.Status.SHIPPED]
    ).aggregate(total=Sum(F('quantity') * F('price')))['total'] or Decimal('0.00')
    total_orders = Order.objects.count()
    total_customers = User.objects.filter(role=User.Role.CUSTOMER).count()
    total_sellers = User.objects.filter(role=User.Role.SELLER, is_approved=True).count()

    start_date = timezone.now().date() - timedelta(days=29)
    daily_sales = OrderItem.objects.filter(order__created_at__date__gte=start_date) \
        .annotate(day=TruncDate('order__created_at')).values('day') \
        .annotate(revenue=Sum(F('quantity') * F('price'))).order_by('day')

    top_sellers = User.objects.filter(role=User.Role.SELLER, is_approved=True) \
        .annotate(revenue=Sum(F('products__orderitem__quantity') * F('products__orderitem__price'))) \
        .order_by('-revenue')[:5]

    order_status_counts = Order.objects.values('status').annotate(count=Count('id'))
    status_dict = {entry['status']: entry['count'] for entry in order_status_counts}
    all_statuses = [
        Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PROCESSING,
        Order.Status.SHIPPED, Order.Status.DELIVERED, Order.Status.CANCELLED,
    ]
    status_labels = {
        Order.Status.PENDING: 'Pending', Order.Status.CONFIRMED: 'Confirmed',
        Order.Status.PROCESSING: 'Processing', Order.Status.SHIPPED: 'Shipped',
        Order.Status.DELIVERED: 'Delivered', Order.Status.CANCELLED: 'Cancelled',
    }
    progress_labels = [status_labels[s] for s in all_statuses]
    progress_data = [status_dict.get(s, 0) for s in all_statuses]

    context = {
        'total_revenue': total_revenue,
        'escrow_funds': escrow_funds,
        'total_orders': total_orders,
        'total_customers': total_customers,
        'total_sellers': total_sellers,
        'pending_sellers_count': pending_sellers_count,
        'chart_labels': [d['day'].strftime('%b %d') for d in daily_sales],
        'chart_data': [float(d['revenue'] or 0) for d in daily_sales],
        'top_sellers': top_sellers,
        'progress_labels': json.dumps(progress_labels),
        'progress_data': json.dumps(progress_data),
        'admin_registry': _get_admin_registry_data(),
    }
    return render(request, 'admin_dashboard.html', context)


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_log_viewer(request):
    log_file_path = os.path.join(settings.BASE_DIR, 'logs', 'stripe_errors.log')
    lines = []
    try:
        if os.path.exists(log_file_path):
            with open(log_file_path, 'r') as f:
                lines = f.readlines()[-100:]
                lines.reverse()
        else:
            lines = ["Log file has not been created yet. No errors recorded."]
    except Exception as e:
        lines = [f"Error reading log file: {str(e)}"]
    return render(request, 'admin_log_viewer.html', {
        'logs': lines,
        'log_filename': 'stripe_errors.log'
    })


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_reset_password(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        if not new_password:
            messages.error(request, "Password cannot be empty.")
            return redirect('admin_reset_password', user_id=user_id)
        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return redirect('admin_reset_password', user_id=user_id)
        target_user.set_password(new_password)
        target_user.save()
        try:
            send_mail(
                subject='Your password has been reset by an administrator',
                message=f'Hello {target_user.fullname},\n\nYour account password has been reset.\nYour new password is: {new_password}\n\nPlease log in and change it immediately.\n\nBest regards,\nLuxMarket Team',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[target_user.email],
                fail_silently=True,
            )
            messages.success(request, f"Password for {target_user.email} has been reset and emailed.")
        except Exception:
            messages.success(request, f"Password for {target_user.email} has been reset (email notification failed).")
        return redirect(request.META.get('HTTP_REFERER', 'admin_customer_list'))
    return render(request, 'admin_reset_password.html', {'target_user': target_user})


# ==================== BULK ACTIONS ====================

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_seller_bulk_action(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids')
        action = request.POST.get('action')
        if not ids:
            messages.warning(request, "Hiç bir satyjy saýlanmady.")
            return redirect('admin_seller_management')
        sellers = User.objects.filter(id__in=ids, role=User.Role.SELLER)
        try:
            with transaction.atomic():
                if action == 'approve':
                    count = sellers.update(is_approved=True)
                    messages.success(request, f"{count} sany satyjy tassyklandy.")
                elif action == 'reject':
                    count = sellers.update(is_active=False)
                    messages.warning(request, f"{count} sany satyjy hasaby ýapyldy.")
                elif action == 'delete':
                    deleted, _ = sellers.delete()
                    messages.success(request, f"{deleted} sany satyjy öçürildi.")
                else:
                    messages.error(request, "Nädogry hereket.")
        except ProtectedError:
            messages.error(request, "Käbir satyjylaryň önümleri ýa-da sargytlary bar, olary öçürip bolmaýar.")
        except Exception as e:
            messages.error(request, f"Ýalňyşlyk ýüze çykdy: {str(e)}")
    return redirect('admin_seller_management')


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_customer_bulk_action(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids')
        action = request.POST.get('action')
        if not ids:
            messages.warning(request, "Hiç bir müşderi saýlanmady.")
            return redirect('admin_customer_list')
        customers = User.objects.filter(id__in=ids, role=User.Role.CUSTOMER)
        try:
            with transaction.atomic():
                if action == 'activate':
                    count = customers.update(is_active=True)
                    messages.success(request, f"{count} sany müşderi hasaby işjeňleşdirildi.")
                elif action == 'deactivate':
                    count = customers.update(is_active=False)
                    messages.warning(request, f"{count} sany müşderi hasaby ýapyldy.")
                elif action == 'delete':
                    deleted, _ = customers.delete()
                    messages.success(request, f"{deleted} sany müşderi hasaby öçürildi.")
                else:
                    messages.error(request, "Nädogry hereket.")
        except ProtectedError:
            messages.error(request, "Käbir müşderileriň sargytlary bar, öçürip bolmaýar.")
        except Exception as e:
            messages.error(request, f"Ýalňyşlyk ýüze çykdy: {str(e)}")
    return redirect('admin_customer_list')


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_review_bulk_action(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids')
        if not ids:
            messages.warning(request, "Hiç bir syn saýlanmady.")
            return redirect('admin_review_list')
        if request.POST.get('action') == 'delete':
            try:
                with transaction.atomic():
                    deleted, _ = Review.objects.filter(id__in=ids).delete()
                    messages.success(request, f"{deleted} sany syn öçürildi.")
            except Exception as e:
                messages.error(request, f"Öçürmekde säwlik: {str(e)}")
        else:
            messages.error(request, "Nädogry hereket.")
    return redirect('admin_review_list')


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_favorite_bulk_action(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids')
        if not ids:
            messages.warning(request, "Hiç bir halanan ýazgysy saýlanmady.")
            return redirect('admin_favorite_list')
        if request.POST.get('action') == 'delete':
            try:
                with transaction.atomic():
                    deleted, _ = Favorite.objects.filter(id__in=ids).delete()
                    messages.success(request, f"{deleted} sany halanan önüm aýryldy.")
            except Exception as e:
                messages.error(request, f"Öçürmekde säwlik: {str(e)}")
        else:
            messages.error(request, "Nädogry hereket.")
    return redirect('admin_favorite_list')


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_product_bulk_action(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids')
        action = request.POST.get('action')
        if not ids:
            messages.warning(request, "No products selected.")
            return redirect('admin_product_list')
        products = Product.objects.filter(id__in=ids)
        try:
            with transaction.atomic():
                if action == 'activate':
                    count = products.update(available=True)
                    messages.success(request, f"Activated {count} products.")
                elif action == 'hide':
                    count = products.update(available=False)
                    messages.success(request, f"Hidden {count} products.")
                elif action == 'delete':
                    deleted, _ = products.delete()
                    messages.success(request, f"Deleted {deleted} products.")
        except ProtectedError:
            messages.error(request, "Some products could not be deleted because they are linked to orders.")
    return redirect('admin_product_list')


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_category_bulk_action(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids')
        if request.POST.get('action') == 'delete':
            try:
                with transaction.atomic():
                    Category.objects.filter(id__in=ids).delete()
                    messages.success(request, "Categories deleted.")
            except ProtectedError:
                messages.error(request, "Cannot delete some categories because they contain products.")
    return redirect('admin_category_list')


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_brand_bulk_action(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids')
        if request.POST.get('action') == 'delete':
            try:
                with transaction.atomic():
                    Brand.objects.filter(id__in=ids).delete()
                    messages.success(request, "Brands deleted.")
            except ProtectedError:
                messages.error(request, "Cannot delete some brands because they are linked to products.")
    return redirect('admin_brand_list')


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_order_bulk_action(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids')
        action = request.POST.get('action')
        orders = Order.objects.filter(id__in=ids)
        try:
            with transaction.atomic():
                if action in dict(Order.Status.choices).keys():
                    count = orders.update(status=action)
                    if action == Order.Status.DELIVERED:
                        orders.update(funds_released=True)
                    messages.success(request, f"Updated {count} orders to {action}.")
                elif action == 'delete':
                    deleted, _ = orders.delete()
                    messages.success(request, f"Deleted {deleted} order records.")
        except ProtectedError:
            messages.error(request, "Some orders are protected by payment records.")
    return redirect('order_list')


@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_payment_bulk_action(request):
    if request.method == 'POST':
        ids = request.POST.getlist('ids')
        if request.POST.get('action') == 'delete':
            try:
                with transaction.atomic():
                    Payment.objects.filter(id__in=ids).delete()
                    messages.success(request, "Payment records deleted.")
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
    return redirect('admin_payment_list')


# ==================== API BULK SUMMARY ====================

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def api_admin_bulk_summary(request):
    """
    Provides a dynamic aggregation of products selected for bulk action.
    Optimized using GROUP BY at the database level to prevent N+1 issues.
    """
    raw_ids = request.GET.get('ids', '').split(',')
    product_ids = [pid for pid in raw_ids if pid.isdigit()]

    if not product_ids:
        return JsonResponse({
            'total_selected': 0,
            'categories': [],
            'brands': []
        })

    selection = Product.objects.filter(id__in=product_ids)

    category_counts = list(selection.values(name=F('category__name'))
                           .annotate(count=Count('id'))
                           .order_by('-count'))

    brand_counts = list(selection.values(name=F('brand__name'))
                        .annotate(count=Count('id'))
                        .order_by('-count'))

    return JsonResponse({
        'total_selected': selection.count(),
        'categories': category_counts,
        'brands': brand_counts
    })


# ==================== STANDARD ADMIN LIST VIEWS ====================

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_customer_list(request):
    customers = User.objects.filter(role=User.Role.CUSTOMER).prefetch_related('orders')
    q = request.GET.get('q', '').strip()
    if q: customers = customers.filter(Q(fullname__icontains=q) | Q(email__icontains=q))
    customers = apply_sorting(request, customers, default_order='-id')
    page_obj = paginate_queryset(request, customers, page_size=15)
    return render(request, 'admin_customer_list.html', {'customers': page_obj, 'q': q})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_payment_list(request):
    payments = Payment.objects.select_related('order', 'order__customer').order_by('-paid_at')
    status = request.GET.get('status')
    q = request.GET.get('q', '').strip()
    if status: payments = payments.filter(status=status)
    if q: payments = payments.filter(Q(id__icontains=q) | Q(order__order_id__icontains=q) | Q(order__customer__email__icontains=q) | Q(order__customer__fullname__icontains=q)).distinct()
    payments = apply_sorting(request, payments, default_order='-paid_at')
    page_obj = paginate_queryset(request, payments, page_size=15)
    return render(request, 'admin_payment_list.html', {'payments': page_obj, 'q': q, 'status': status})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_seller_management(request):
    q = request.GET.get('q', '').strip()
    pending_sellers = User.objects.filter(role=User.Role.SELLER, is_approved=False)
    approved_sellers = User.objects.filter(role=User.Role.SELLER, is_approved=True)
    if q:
        search_filter = Q(fullname__icontains=q) | Q(email__icontains=q)
        pending_sellers = pending_sellers.filter(search_filter)
        approved_sellers = approved_sellers.filter(search_filter)
    pending_sellers = apply_sorting(request, pending_sellers, default_order='-id')
    approved_sellers = apply_sorting(request, approved_sellers, default_order='-id')
    pending_page_obj = paginate_queryset(request, pending_sellers, page_size=5)
    approved_page_obj = paginate_queryset(request, approved_sellers, page_size=10)
    return render(request, 'admin_seller_management.html', {'pending_sellers': pending_page_obj, 'approved_sellers': approved_page_obj, 'q': q})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def approve_seller(request, user_id):
    seller = get_object_or_404(User, id=user_id, role=User.Role.SELLER)
    seller.is_approved = True
    seller.save()
    messages.success(request, f"Seller {seller.fullname} has been approved.")
    return redirect('admin_seller_management')

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def reject_seller(request, user_id):
    seller = get_object_or_404(User, id=user_id, role=User.Role.SELLER)
    seller.is_active = False
    seller.save()
    messages.warning(request, f"Seller {seller.fullname} rejected and deactivated.")
    return redirect('admin_seller_management')

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def export_payments_csv(request):
    payments = Payment.objects.all()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payments.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'Order', 'Amount', 'Status', 'Date'])
    for p in payments:
        writer.writerow([p.id, p.order.display_id, p.amount, p.status, p.paid_at])
    return response

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_brand_list(request):
    brands = Brand.objects.all().order_by('name')
    return render(request, 'admin_brand_list.html', {'brands': brands})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_brand_add(request):
    if request.method == 'POST':
        form = BrandForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Brand created successfully.")
            return redirect('admin_brand_list')
    else:
        form = BrandForm()
    return render(request, 'admin_brand_form.html', {'form': form, 'title': 'Add Brand'})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_brand_edit(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        form = BrandForm(request.POST, request.FILES, instance=brand)
        if form.is_valid():
            form.save()
            messages.success(request, "Brand updated.")
            return redirect('admin_brand_list')
    else:
        form = BrandForm(instance=brand)
    return render(request, 'admin_brand_form.html', {'form': form, 'title': 'Edit Brand'})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_brand_delete(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        try:
            brand.delete()
            messages.success(request, "Brand deleted.")
        except ProtectedError:
            messages.error(request, "Cannot delete brand because it has products.")
    return redirect('admin_brand_list')

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_category_list(request):
    categories = Category.objects.all().order_by('name')
    return render(request, 'admin_category_list.html', {'categories': categories})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_category_add(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Category created.")
            return redirect('admin_category_list')
    else:
        form = CategoryForm()
    return render(request, 'admin_category_form.html', {'form': form, 'title': 'Add Category'})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "Category updated.")
            return redirect('admin_category_list')
    else:
        form = CategoryForm(instance=category)
    return render(request, 'admin_category_form.html', {'form': form, 'title': 'Edit Category'})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        try:
            category.delete()
            messages.success(request, "Category deleted.")
        except ProtectedError:
            messages.error(request, "Cannot delete category because it has products.")
    return redirect('admin_category_list')

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_product_list(request):
    products = Product.objects.select_related('category', 'seller', 'brand').prefetch_related('images')
    q = request.GET.get('q', '').strip()
    category_id = request.GET.get('category')
    seller_id = request.GET.get('seller')
    brand_id = request.GET.get('brand')
    status = request.GET.get('status')
    if q: products = products.filter(Q(name__icontains=q) | Q(seller__fullname__icontains=q) | Q(brand__name__icontains=q))
    if category_id: products = products.filter(category_id=category_id)
    if seller_id: products = products.filter(seller_id=seller_id)
    if brand_id: products = products.filter(brand_id=brand_id)
    if status == 'active': products = products.filter(available=True)
    elif status == 'hidden': products = products.filter(available=False)
    products = apply_sorting(request, products, default_order='-created')
    page_obj = paginate_queryset(request, products, page_size=10)
    return render(request, 'admin_product_list.html', {
        'products': page_obj,
        'categories': Category.objects.all(),
        'sellers': User.objects.filter(role=User.Role.SELLER, is_approved=True),
        'brands': Brand.objects.all(),
        'q': q,
    })

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_product_add(request):
    if request.method == 'POST':
        form = AdminProductForm(request.POST)
        formset = ProductImageFormSet(request.POST, request.FILES, instance=form.instance)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, 'Product added.')
            return redirect('admin_product_list')
    else:
        form = AdminProductForm()
        formset = ProductImageFormSet()
    return render(request, 'seller_product_form.html', {'form': form, 'formset': formset, 'title': 'Add Product'})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_product_edit(request, uuid):
    product = get_object_or_404(Product, uuid=uuid)
    if request.method == 'POST':
        form = AdminProductForm(request.POST, instance=product)
        formset = ProductImageFormSet(request.POST, request.FILES, instance=product)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, 'Product updated.')
            return redirect('admin_product_list')
    else:
        form = AdminProductForm(instance=product)
        formset = ProductImageFormSet(instance=product)
    return render(request, 'seller_product_form.html', {'form': form, 'formset': formset, 'title': 'Edit Product', 'product': product})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_product_toggle_availability(request, uuid):
    product = get_object_or_404(Product, uuid=uuid)
    product.available = not product.available
    product.save()
    messages.success(request, "Product status updated.")
    return redirect('admin_product_list')

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_product_delete(request, uuid):
    product = get_object_or_404(Product, uuid=uuid)
    if request.method == 'POST':
        try:
            product.delete()
            messages.success(request, "Product deleted.")
        except ProtectedError:
            messages.error(request, "Product cannot be deleted because it has orders.")
    return redirect('admin_product_list')

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_review_list(request):
    reviews = Review.objects.select_related('product', 'user').all()
    q = request.GET.get('q', '').strip()
    rating_filter = request.GET.get('rating')
    if q: reviews = reviews.filter(Q(product__name__icontains=q) | Q(user__fullname__icontains=q) | Q(comment__icontains=q))
    if rating_filter:
        if rating_filter == 'low': reviews = reviews.filter(rating__lte=2)
        elif rating_filter.isdigit(): reviews = reviews.filter(rating=int(rating_filter))
    reviews = apply_sorting(request, reviews, default_order='-created_at')
    page_obj = paginate_queryset(request, reviews, page_size=15)
    return render(request, 'admin_review_list.html', {'reviews': page_obj, 'q': q, 'rating_filter': rating_filter})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_review_delete(request, pk):
    review = get_object_or_404(Review, pk=pk)
    if request.method == 'POST':
        review.delete()
        messages.success(request, "Review deleted.")
    return redirect('admin_review_list')

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_favorite_list(request):
    favorites = Favorite.objects.select_related('user', 'product').all()
    q = request.GET.get('q', '').strip()
    if q: favorites = favorites.filter(Q(product__name__icontains=q) | Q(user__fullname__icontains=q))
    favorites = apply_sorting(request, favorites, default_order='-created_at')
    page_obj = paginate_queryset(request, favorites, page_size=20)
    return render(request, 'admin_favorite_list.html', {'favorites': page_obj, 'q': q})

@login_required
@user_passes_test(lambda u: u.role == User.Role.ADMIN, login_url='login')
def admin_seller_delete(request, user_id):
    seller = get_object_or_404(User, id=user_id, role=User.Role.SELLER)
    if request.method == 'POST':
        seller.delete()
        messages.success(request, "Seller deleted.")
    return redirect('admin_seller_management')


def terms_of_use(request):
    return render(request, 'terms_of_use.html')

def privacy_policy(request):
    return render(request, 'privacy_policy.html')

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .models import Favorite, Product
import json

@login_required
@require_POST
def wishlist_bulk_remove(request):
    try:
        data = json.loads(request.body)
        favorite_ids = data.get('favorite_ids', [])
        if not favorite_ids:
            return JsonResponse({'success': False, 'error': 'Hiç hili ID iberilmedi.'}, status=400)
        
        # Ulanyja degişli Favorite ýazgylaryny poz
        deleted, _ = Favorite.objects.filter(
            user=request.user,
            product_id__in=favorite_ids
        ).delete()
        
        return JsonResponse({'success': True, 'deleted_count': deleted})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)