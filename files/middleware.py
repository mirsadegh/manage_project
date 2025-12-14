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
        """Get client's IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip