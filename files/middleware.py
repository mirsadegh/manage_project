# files/middleware.py

import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('files')


class FileAccessLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log file access attempts.
    Tracks downloads, previews, and access denials.
    """
    
    def process_response(self, request, response):
        """Log file access"""
        
        # Only log file-related endpoints
        if '/attachments/' in request.path and '/download/' in request.path:
            user = getattr(request, 'user', None)
            user_info = user.username if user and user.is_authenticated else 'Anonymous'
            
            if response.status_code == 200:
                logger.info(
                    f"File downloaded: {request.path} by {user_info} from {self.get_client_ip(request)}"
                )
            elif response.status_code == 403:
                logger.warning(
                    f"File access denied: {request.path} by {user_info} from {self.get_client_ip(request)}"
                )
            elif response.status_code == 404:
                logger.warning(
                    f"File not found: {request.path} by {user_info} from {self.get_client_ip(request)}"
                )
        
        return response
    
    def get_client_ip(self, request):
        """Get client's IP address, honoring X-Forwarded-For only from
        trusted proxies (PR-3 Fix #9). Delegates to the WS proxy helper,
        building an ASGI-style scope from the Django request.
        """
        from config.proxies import get_client_ip as _resolve
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