from django.utils import timezone
from django.core.cache import cache

class LastSeenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Throttling database updates to once every 5 minutes (300 seconds)
            # to significantly reduce database load
            cache_key = f"last_seen_sync_{request.user.id}"
            if not cache.get(cache_key):
                request.user.last_seen = timezone.now()
                request.user.save(update_fields=['last_seen'])
                cache.set(cache_key, True, 300) 
        return self.get_response(request)