from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

class BurstRateThrottle(UserRateThrottle):
    """
    Burst rate limiting - 60 requests per minute.
    Prevents rapid-fire requests.
    """
    scope = 'burst'
    rate = '60/min'


class SustainedRateThrottle(UserRateThrottle):
    """
    Sustained rate limiting - 1000 requests per day.
    Prevents long-term abuse.
    """
    scope = 'sustained'
    rate = '1000/day'


class AnonymousUserThrottle(AnonRateThrottle):
    """
    Rate limiting for anonymous users - 20 requests per hour.
    Very restrictive for unauthenticated access.
    """
    scope = 'anon'
    rate = '20/hour'


class LoginRateThrottle(AnonRateThrottle):
    """
    Rate limiting for login attempts.
    Uses IP address for anonymous users.
    """
    scope = 'login'
    
    def get_cache_key(self, request, view):
        # Use IP address for rate limiting login attempts
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request)
        }

class PasswordResetRateThrottle(AnonRateThrottle):
    """Rate limiting for password reset requests."""
    scope = 'password_reset'




class ProjectCreationThrottle(UserRateThrottle):
    """
    Rate limiting for project creation - 10 per hour.
    Prevents spam project creation.
    """
    scope = 'project_creation'
    rate = '10/hour'


class TaskCreationThrottle(UserRateThrottle):
    """
    Rate limiting for task creation - 50 per hour.
    """
    scope = 'task_creation'
    rate = '50/hour'















