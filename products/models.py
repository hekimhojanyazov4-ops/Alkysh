import uuid
from decimal import Decimal
from django.utils import timezone  # Dogry import
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db.models import CheckConstraint, Sum, F
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.validators import FileExtensionValidator
from django.urls import reverse


def validate_file_size(value):
    limit = 5 * 1024 * 1024  # 5MB
    if value.size > limit:
        raise ValidationError('File too large. Size should not exceed 5 MiB.')


class UserManager(BaseUserManager):
    def create_user(self, email, fullname, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, fullname=fullname, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, fullname, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, fullname, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'admin'
        SELLER = 'SELLER', 'seller'
        CUSTOMER = 'CUSTOMER', 'customer'

    fullname = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    user_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False)
    verification_document = models.FileField(
        upload_to='seller_docs/',
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png']),
            validate_file_size
        ]
    )
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['fullname']
    objects = UserManager()

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.fullname

    def get_short_name(self):
        return self.fullname.split()[0] if self.fullname else self.email

    def save(self, *args, **kwargs):
        skip_notification = kwargs.pop('skip_approval_notification', False)
        # Check if this is a new seller registration awaiting approval
        is_new_seller = self._state.adding and self.role == self.Role.SELLER and not self.is_approved

        super().save(*args, **kwargs)

        if is_new_seller and not skip_notification:
            # Fetch all active administrator emails
            admin_emails = list(User.objects.filter(
                role=User.Role.ADMIN, is_active=True
            ).values_list('email', flat=True))

            if admin_emails:
                site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
                admin_url = f"{site_url}{reverse('admin_seller_management')}"

                context = {
                    'seller_name': self.fullname,
                    'seller_email': self.email,
                    'admin_url': admin_url,
                    # Eger created_at ýok bolsa, uuid bilen çalyşýar
                    'timestamp': self.created_at if hasattr(self, 'created_at') else uuid.uuid4(),
                }

                html_message = render_to_string('emails/new_seller_notification.html', context)
                plain_message = strip_tags(html_message)

                send_mail(
                    subject=f"New Seller Application: {self.fullname}",
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=admin_emails,
                    fail_silently=True,
                    html_message=html_message
                )


class Brand(models.Model):
    name = models.CharField(max_length=200)
    logo = models.ImageField(upload_to='logos', blank=True, null=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    icon = models.ImageField(upload_to='category_images/', blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Category, related_name='products', on_delete=models.CASCADE)
    brand = models.ForeignKey(Brand, related_name='products', on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, default=None)
    available = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    uploaded = models.DateTimeField(auto_now=True)
    seller = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='products',
        limit_choices_to={'role': User.Role.SELLER}
    )

    def clean(self):
        if self.discount_price is not None and self.discount_price >= self.price:
            raise ValidationError("Discount price must be less than the original price.")
        if self.seller and self.seller.role != User.Role.SELLER:
            raise ValidationError("Seller must have the role of 'SELLER'.")

    class Meta:
        ordering = ['-created']
        constraints = [
            CheckConstraint(
                check=models.Q(discount_price__lt=models.F('price')) | models.Q(discount_price__isnull=True),
                name='discount_price_less_than_price_or_null'
            )
        ]

    def __str__(self):
        return self.name

    @property
    def effective_price(self):
        return self.discount_price if self.discount_price is not None else self.price


class ProductImage(models.Model):
    image = models.ImageField(upload_to='product_images/')
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)

    def __str__(self):
        return f"Image for {self.product.name}"


class Cart(models.Model):
    customer = models.OneToOneField(
        User, related_name='cart', on_delete=models.CASCADE,
        limit_choices_to={'role': User.Role.CUSTOMER}
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_price(self):
        return self.items.aggregate(
            total=Sum(F('quantity') * F('product__price'), output_field=models.DecimalField())
        )['total'] or Decimal('0.00')


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cart', 'product'], name='unique_cart_product')
        ]

    def get_cost(self):
        return self.product.effective_price * self.quantity

    @property
    def line_total(self):
        return self.get_cost()


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'pending'
        CONFIRMED = 'CONFIRMED', 'confirmed'
        PROCESSING = 'PROCESSING', 'processing'
        SHIPPED = 'SHIPPED', 'shipped'
        DELIVERED = 'DELIVERED', 'delivered'
        CANCELLED = 'CANCELLED', 'cancelled'

    customer = models.ForeignKey(
        User, related_name='orders', on_delete=models.CASCADE,
        limit_choices_to={'role': User.Role.CUSTOMER}
    )
    payment_method = models.CharField(max_length=50, default='Cash on Delivery')
    stripe_session_id = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    funds_released = models.BooleanField(default=False)
    order_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, primary_key=False)
    display_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def save(self, *args, **kwargs):
        if not self.order_id:
            self.order_id = uuid.uuid4()
        if not self.display_id:
            today_str = timezone.now().strftime('%Y%m%d')  # Indi dogry işleýär
            uuid_short = str(self.order_id)[:8].upper()
            self.display_id = f"{today_str}-{uuid_short}"
        super().save(*args, **kwargs)

    @property
    def public_id(self):
        return str(self.order_id)

    def update_total(self):
        new_total = self.items.aggregate(
            total=Sum(F('quantity') * F('price'), output_field=models.DecimalField())
        )['total'] or 0.00
        self.total_price = new_total
        self.save(update_fields=['total_price'])

    def __str__(self):
        return f"Order #{self.display_id or self.order_id}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['order', 'product'], name='unique_order_product')
        ]

    def get_cost(self):
        return self.price * self.quantity

    @property
    def line_total(self):
        return self.get_cost()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.order.update_total()

    def delete(self, *args, **kwargs):
        order = self.order
        super().delete(*args, **kwargs)
        order.update_total()

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"


class Payment(models.Model):
    class PaymentStatus(models.TextChoices):
        SUCCESS = 'success'
        PENDING = 'pending'
        FAILED = 'failed'

    order = models.ForeignKey(Order, related_name='payments', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    paid_at = models.DateTimeField(auto_now_add=True)


class Favorite(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='favorites',
        limit_choices_to={'role': User.Role.CUSTOMER}
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'product'], name='unique_user_favorite')
        ]