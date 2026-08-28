import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('permissions')

class PermissionLoggingMiddleware(MiddlewareMixin):
    """Middleware to log permission denials."""
    
    def process_response(self, request, response):
        # Log 403 Forbidden responses
        if response.status_code == 403:
            user = getattr(request, 'user', None)
            user_info = f"{user.username} (Role: {user.role})" if user and user.is_authenticated else "Anonymous"
            
            logger.warning(
                f"Permission denied: {request.method} {request.path} "
                f"by {user_info} from IP: {self.get_client_ip(request)}"
            )
        
        return response
    
    def get_client_ip(self, request):
        """Get client's IP address, honoring X-Forwarded-For only from
        trusted proxies (PR-3 Fix #9). Delegates to the WS proxy helper,
        building an ASGI-style scope from the Django request.
        """
        from .proxies import get_client_ip as _resolve
        scope = {
            'client': (request.META.get('REMOTE_ADDR', ''), 0),
            'headers': [
                (
                    # Django prefixes with HTTP_; strip it AND convert
                    # underscores to hyphens (WSGI → HTTP convention).
                    k[len('HTTP_'):].lower().replace('_', '-').encode('latin-1'),
                    str(v).encode('latin-1'),
                )
                for k, v in request.META.items()
                if k.startswith('HTTP_') and k != 'HTTP_HOST'
            ],
        }
        return _resolve(scope)



