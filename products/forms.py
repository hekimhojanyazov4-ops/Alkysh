# forms.py

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError
from .models import User, Product, CartItem, ProductImage, Category, Brand

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB


class CustomUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(
        choices=[c for c in User.Role.choices if c[0] != User.Role.ADMIN],
        initial=User.Role.CUSTOMER,
        widget=forms.Select(attrs={
            'class': 'w-full pl-10 pr-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors'
        })
    )
    fullname = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full pl-10 pr-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
            'placeholder': 'Full Name'
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full pl-10 pr-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
            'placeholder': 'Email Address'
        })
    )
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full pl-10 pr-10 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
            'placeholder': 'Password'
        }),
    )
    password2 = forms.CharField(
        label="Confirm Password",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full pl-10 pr-10 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
            'placeholder': 'Confirm Password'
        }),
    )
    verification_document = forms.FileField(
        required=False,
        label="Identity Verification (Sellers only)",
        widget=forms.FileInput(attrs={
            'class': 'w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-lux-50 file:text-lux-700 hover:file:bg-lux-100 dark:file:bg-lux-900/30 dark:file:text-lux-400 transition-colors'
        })
    )

    class Meta:
        model = User
        fields = ('fullname', 'email', 'role', 'verification_document')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def clean_verification_document(self):
        file = self.cleaned_data.get('verification_document')
        if file:
            if file.size > MAX_UPLOAD_SIZE:
                raise ValidationError("File size must be under 5MB.")
            if not file.name.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png')):
                raise ValidationError("Unsupported file format. Please upload PDF or Images.")
        return file

    def clean_role(self):
        role = self.cleaned_data.get('role')
        if role == User.Role.ADMIN:
            raise ValidationError("You cannot register as an administrator.")
        return role

    def save(self, commit=True):
        user = super().save(commit=False)
        if user.role == User.Role.SELLER:
            user.is_approved = False
        else:
            user.is_approved = True

        if commit:
            user.save()
        return user


class CustomAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full pl-10 pr-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
            'placeholder': 'Email'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full pl-10 pr-10 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
            'placeholder': 'Password'
        })
    )


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ['name', 'logo']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors'
            }),
            'logo': forms.FileInput(attrs={
                'class': 'w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-lux-50 file:text-lux-700 hover:file:bg-lux-100 dark:file:bg-lux-900/30 dark:file:text-lux-400 transition-colors'
            }),
        }


# forms.py

from django import forms
from .models import Category

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'slug']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
                'placeholder': 'Kategoriýa ady'
            }),
            'slug': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
                'placeholder': 'Slug (boş goýsaňyz awtomatik dörediler)'
            }),
        }
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['category', 'brand', 'name', 'price', 'description', 'discount_price', 'available']
        widgets = {
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors'
            }),
            'brand': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors'
            }),
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
                'placeholder': 'Product Name'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
                'placeholder': '0.00'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
                'rows': 4,
                'placeholder': 'Describe your luxury item...'
            }),
            'discount_price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors',
                'placeholder': 'Optional discount price'
            }),
            'available': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 rounded text-lux-600 focus:ring-lux-500 border-gray-300 dark:border-gray-700 dark:bg-gray-900'
            }),
        }
        labels = {
            'discount_price': 'Discount Price (leave blank if none)',
            'available': 'In Stock',
        }

    def clean(self):
        cleaned_data = super().clean()
        price = cleaned_data.get('price')
        discount = cleaned_data.get('discount_price')
        if discount is not None and discount >= price:
            raise ValidationError("Discount price must be less than the original price.")
        return cleaned_data


class AdminProductForm(ProductForm):
    seller = forms.ModelChoiceField(
        queryset=User.objects.filter(role=User.Role.SELLER, is_approved=True),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border border-gray-200 dark:border-gray-700 dark:bg-gray-900 dark:text-white rounded-xl focus:ring-2 focus:ring-lux-400 focus:outline-none transition-colors'
        }),
        required=True,
        empty_label="Select a Seller"
    )

    class Meta(ProductForm.Meta):
        fields = ProductForm.Meta.fields + ['seller']


class ProductImageForm(forms.ModelForm):
    """Custom inline form for product images with hidden file input.
    The visible button is rendered via a <label> in the template.
    """
    class Meta:
        model = ProductImage
        fields = ['image']
        widgets = {
            'image': forms.ClearableFileInput(attrs={
                'class': 'hidden',   # hide the raw input, it will be triggered by the label
            })
        }


class BaseProductImageFormSet(forms.BaseInlineFormSet):
    def clean(self):
        """Check that at least one image has been provided and not marked for deletion."""
        super().clean()
        if any(self.errors):
            return

        images_count = 0
        for form in self.forms:
            if form.cleaned_data and form.cleaned_data.get('image') and not form.cleaned_data.get('DELETE'):
                images_count += 1

        if images_count < 1:
            raise ValidationError(
                "Every product must have at least one image. Please upload at least one image."
            )


ProductImageFormSet = forms.inlineformset_factory(
    Product,
    ProductImage,
    form=ProductImageForm,         # use the custom form with hidden file widget
    fields=('image',),
    extra=3,
    can_delete=True,
    formset=BaseProductImageFormSet
)


class CartItemUpdateForm(forms.ModelForm):
    class Meta:
        model = CartItem
        fields = ['quantity']
        widgets = {
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'style': 'width: 80px;'
            }),
        }

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty < 1:
            raise ValidationError("Quantity must be at least 1.")
        return qty