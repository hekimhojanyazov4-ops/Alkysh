from django.contrib import admin

def admin_registry(request):
    """
    Django admin registry-däki ähli modelleri tapyp, templates-lere iberýär.
    Diňe admin ulanyjylar üçin işleýär.
    """
    if not request.user.is_authenticated or not (request.user.is_staff or getattr(request.user, 'role', '') == 'ADMIN'):
        return {}

    registry_data = {}
    for model_cls in admin.site._registry:
        app_label = model_cls._meta.app_label
        if app_label not in registry_data:
            registry_data[app_label] = []
        
        registry_data[app_label].append({
            'model_name': model_cls._meta.model_name,
            'verbose_name': model_cls._meta.verbose_name_plural.capitalize(),
            'app_label': app_label,
        })
    return {'admin_registry': registry_data}