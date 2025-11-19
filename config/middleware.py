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
        """Get client's IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip



