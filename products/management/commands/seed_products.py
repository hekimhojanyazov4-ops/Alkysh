import requests
import uuid
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from products.models import User, Category, Brand, Product, ProductImage
from decimal import Decimal
from django.core.files.base import ContentFile
import base64

class Command(BaseCommand):
    help = 'Seeds the database with initial luxury brands, categories, and products'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding data...')

        # Fallback: A small 1x1 transparent PNG if image downloads fail
        pixel_png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")

        def download_image(seed):
            """Fetch a realistic product image or return pixel on failure."""
            try:
                # Using Lorem Picsum for realistic luxury-themed placeholders
                url = f"https://picsum.photos/seed/{seed}/800/1000"
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                return ContentFile(resp.content, name=f"{uuid.uuid4().hex}.jpg")
            except Exception:
                return ContentFile(pixel_png, name="placeholder.png")

        # 1. Create or get a Seller
        seller, created = User.objects.get_or_create(
            email='seller@luxmarket.com',
            defaults={
                'fullname': 'Lux Seller Official',
                'role': User.Role.SELLER,
                'is_approved': True,
                'is_active': True
            }
        )
        if created:
            seller.set_password('password123')
            seller.save()
            self.stdout.write(self.style.SUCCESS('Created seller: seller@luxmarket.com'))

        # 2. Create Categories
        categories_data = [
            ('Timepieces', 'bi-watch', 'The intersection of high engineering and artistic expression. Discover horological masterpieces featuring heritage movements and timeless complications.'),
            ('Leather Goods', 'bi-handbag', 'Defined by impeccable craftsmanship and rare materials. Explore our collection of iconic handbags where traditional techniques meet contemporary luxury.'),
            ('Fine Jewelry', 'bi-gem', 'Eternal brilliance captured in precious stones and metals. Find jewelry that tells a story of elegance, distinction, and master-level artistry.'),
            ('High Fashion', 'bi-stars', 'The ultimate expression of sartorial excellence. Experience curated collections from global runways, featuring couture-level craftsmanship.')
        ]
        category_map = {}
        for name, icon, desc in categories_data:
            cat, created = Category.objects.get_or_create(
                name=name,
                defaults={'slug': slugify(name), 'icon': icon, 'description': desc}
            )
            if not created:
                cat.icon = icon
                cat.description = desc
                cat.save()

            category_map[name] = cat
            if created:
                self.stdout.write(f'Created category: {name}')

        # 3. Create Brands
        brands_names = ['Patek Philippe', 'Hermès', 'Van Cleef & Arpels', 'Chanel']
        brand_map = {}
        for name in brands_names:
            brand, created = Brand.objects.get_or_create(
                name=name
            )
            if created:
                logo_img = download_image(f"brand-{slugify(name)}")
                brand.logo.save(f"{slugify(name)}_logo.png", logo_img, save=True)
                self.stdout.write(f'Created brand: {name}')
            brand_map[name] = brand

        # 4. Create Sample Products
        products_to_add = [
            {
                'name': 'Nautilus 5711/1A',
                'category': category_map['Timepieces'],
                'brand': brand_map['Patek Philippe'],
                'price': Decimal('120000.00'),
                'description': 'An iconic steel sports watch with a blue ribbed dial.',
                'seller': seller,
                'available': True
            },
            {
                'name': 'Birkin 30 Togo',
                'category': category_map['Leather Goods'],
                'brand': brand_map['Hermès'],
                'price': Decimal('25000.00'),
                'discount_price': Decimal('24500.00'),
                'description': 'Gold Togo leather with palladium hardware.',
                'seller': seller,
                'available': True
            },
            {
                'name': 'Alhambra Bracelet',
                'category': category_map['Fine Jewelry'],
                'brand': brand_map['Van Cleef & Arpels'],
                'price': Decimal('4500.00'),
                'description': 'Vintage Alhambra bracelet, 5 motifs, yellow gold, onyx.',
                'seller': seller,
                'available': True
            },
            {
                'name': 'Classic Flap Bag',
                'category': category_map['High Fashion'],
                'brand': brand_map['Chanel'],
                'price': Decimal('10200.00'),
                'description': 'Lambskin & Gold-Tone Metal Black Classic Handbag.',
                'seller': seller,
                'available': True
            }
        ]

        for p_data in products_to_add:
            product_name = p_data.pop('name')
            product, created = Product.objects.get_or_create(
                name=product_name,
                defaults=p_data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Added product: {product.name}'))
                
                # Add multiple images to fulfill "visual representation" requirement and look professional
                for i in range(1, 4):
                    img_data = download_image(f"{slugify(product.name)}-{i}")
                    ProductImage.objects.create(
                        product=product,
                        image=img_data
                    )
                
                self.stdout.write(f'  - Attached 3 images to {product.name}')

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))