from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.exceptions import DenyConnection
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from rest_framework_simplejwt.tokens import AccessToken, TokenError
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from accounts.models import CustomUser
from urllib.parse import parse_qs
import logging
import time

logger = logging.getLogger(__name__)


class TokenValidationResult:
    """Container for token validation results."""
    
    def __init__(self, user=None, error=None, is_valid=False):
        self.user = user or AnonymousUser()
        self.error = error
        self.is_valid = is_valid


@database_sync_to_async
def get_user_from_token(token_string):
    """
    Validate JWT token and return user.
    Includes blacklist checking and caching for performance.
    """
    if not token_string:
        return TokenValidationResult(error="No token provided")
    
    # Check cache first for performance
    cache_key = f"ws_token_{hash(token_string)}"
    cached_user_id = cache.get(cache_key)
    
    if cached_user_id:
        try:
            user = CustomUser.objects.get(id=cached_user_id, is_active=True)
            return TokenValidationResult(user=user, is_valid=True)
        except CustomUser.DoesNotExist:
            cache.delete(cache_key)
    
    try:
        # Validate token
        access_token = AccessToken(token_string)
        user_id = access_token.get('user_id')
        
        if not user_id:
            return TokenValidationResult(error="Invalid token payload")
        
        # Check token expiration
        exp = access_token.get('exp')
        if exp and time.time() > exp:
            return TokenValidationResult(error="Token expired")
        
        # Check if token is blacklisted (via its jti)
        jti = access_token.get('jti')
        if jti:
            try:
                outstanding = OutstandingToken.objects.filter(jti=jti).first()
                if outstanding and BlacklistedToken.objects.filter(token=outstanding).exists():
                    return TokenValidationResult(error="Token has been revoked")
            except Exception:
                pass  # If blacklist check fails, continue with validation
        
        # Get user
        user = CustomUser.objects.get(id=user_id, is_active=True)
        
        # Cache the result (cache for shorter than token lifetime)
        cache_ttl = min(300, max(0, exp - time.time())) if exp else 300
        cache.set(cache_key, user_id, int(cache_ttl))
        
        return TokenValidationResult(user=user, is_valid=True)
    
    except InvalidToken as e:
        logger.warning(f"WebSocket auth failed - Invalid token: {e}")
        return TokenValidationResult(error="Invalid token")
    
    except TokenError as e:
        logger.warning(f"WebSocket auth failed - Token error: {e}")
        return TokenValidationResult(error=str(e))
    
    except CustomUser.DoesNotExist:
        logger.warning(f"WebSocket auth failed - User not found or inactive")
        return TokenValidationResult(error="User not found or inactive")
    
    except Exception as e:
        logger.error(f"WebSocket auth failed - Unexpected error: {e}")
        return TokenValidationResult(error="Authentication failed")


@database_sync_to_async
def invalidate_user_token_cache(user_id):
    """Invalidate cached tokens for a user."""
    # This would require tracking cache keys per user
    # For now, we rely on short cache TTL
    pass


class JWTAuthMiddleware(BaseMiddleware):
    """
    Custom middleware to authenticate WebSocket connections using JWT.
    
    Features:
    - Token extraction from query params or headers
    - Token validation with blacklist checking
    - Connection rate limiting
    - Detailed error handling
    - Support for anonymous connections (configurable)
    
    Usage:
        ws://localhost:8000/ws/notifications/?token=<access_token>
        
    Or with headers:
        Authorization: Bearer <access_token>
    """
    
    # Configuration
    ALLOW_ANONYMOUS = False  # Set to True to allow unauthenticated connections
    RATE_LIMIT_CONNECTIONS = 10  # Max connections per minute per IP
    RATE_LIMIT_WINDOW = 60  # Window in seconds
    
    async def __call__(self, scope, receive, send):
        # Get client IP for rate limiting
        client_ip = self._get_client_ip(scope)
        
        # Check rate limit
        if not await self._check_rate_limit(client_ip):
            logger.warning(f"WebSocket rate limit exceeded for IP: {client_ip}")
            await self._close_connection(send, code=4029, reason="Rate limit exceeded")
            return
        
        # Extract token
        token = self._extract_token(scope)
        
        # Validate token and get user
        validation_result = await get_user_from_token(token)
        
        # Handle authentication result
        if validation_result.is_valid:
            scope['user'] = validation_result.user
            scope['auth_error'] = None
            logger.info(f"WebSocket authenticated for user: {validation_result.user.username}")
        else:
            scope['user'] = AnonymousUser()
            scope['auth_error'] = validation_result.error
            
            if not self.ALLOW_ANONYMOUS:
                logger.warning(f"WebSocket connection denied: {validation_result.error}")
                await self._close_connection(
                    send, 
                    code=4001, 
                    reason=validation_result.error or "Authentication required"
                )
                return
        
        # Store additional auth metadata
        scope['auth'] = {
            'is_authenticated': validation_result.is_valid,
            'client_ip': client_ip,
            'timestamp': time.time(),
        }
        
        return await super().__call__(scope, receive, send)
    
    def _extract_token(self, scope):
        """Extract JWT token from query string or headers."""
        token = None
        
        # Method 1: Query string parameter
        query_string = scope.get('query_string', b'').decode()
        if query_string:
            params = parse_qs(query_string)
            token_list = params.get('token', [])
            if token_list:
                token = token_list[0]
        
        # Method 2: Authorization header
        if not token:
            headers = dict(scope.get('headers', []))
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
            elif auth_header.startswith('bearer '):
                token = auth_header[7:]
        
        # Method 3: Sec-WebSocket-Protocol header (for browsers that can't set custom headers)
        if not token:
            headers = dict(scope.get('headers', []))
            protocol_header = headers.get(b'sec-websocket-protocol', b'').decode()
            if protocol_header:
                protocols = [p.strip() for p in protocol_header.split(',')]
                for protocol in protocols:
                    if protocol.startswith('access_token.'):
                        token = protocol.replace('access_token.', '')
                        break
        
        return token
    
    def _get_client_ip(self, scope):
        """Extract client IP from scope."""
        headers = dict(scope.get('headers', []))
        
        # Check for forwarded headers (when behind proxy)
        x_forwarded_for = headers.get(b'x-forwarded-for', b'').decode()
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        
        x_real_ip = headers.get(b'x-real-ip', b'').decode()
        if x_real_ip:
            return x_real_ip
        
        # Fall back to direct connection
        client = scope.get('client')
        if client:
            return client[0]
        
        return 'unknown'
    
    async def _check_rate_limit(self, client_ip):
        """Check if client has exceeded connection rate limit."""
        cache_key = f"ws_ratelimit_{client_ip}"
        
        @database_sync_to_async
        def check_and_increment():
            current = cache.get(cache_key, 0)
            if current >= self.RATE_LIMIT_CONNECTIONS:
                return False
            cache.set(cache_key, current + 1, self.RATE_LIMIT_WINDOW)
            return True
        
        return await check_and_increment()
    
    async def _close_connection(self, send, code=4000, reason="Connection closed"):
        """Send close frame to reject connection."""
        await send({
            'type': 'websocket.close',
            'code': code,
            'reason': reason,
        })


class JWTAuthMiddlewareStack:
    """
    Convenience wrapper to create the full middleware stack.
    
    Usage:
        application = ProtocolTypeRouter({
            'websocket': JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
        })
    """
    
    def __init__(self, inner):
        self.inner = JWTAuthMiddleware(inner)
    
    def __call__(self, scope):
        return self.inner(scope)


# Optional: Decorator for consumers that require authentication
def websocket_auth_required(consumer_class):
    """
    Decorator to enforce authentication on WebSocket consumers.
    
    Usage:
        @websocket_auth_required
        class MyConsumer(AsyncWebsocketConsumer):
            pass
    """
    original_connect = consumer_class.connect
    
    async def connect(self):
        if not self.scope.get('user') or not self.scope['user'].is_authenticated:
            await self.close(code=4001)
            return
        return await original_connect(self)
    
    consumer_class.connect = connect
    return consumer_class



