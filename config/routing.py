from django.urls import path, re_path
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from .websocket_auth import JWTAuthMiddleware
from notifications.consumers import NotificationConsumer
from projects.consumers import ProjectConsumer

websocket_urlpatterns = [
    path('ws/notifications/', NotificationConsumer.as_asgi()),
    path('ws/projects/<slug:project_slug>/', ProjectConsumer.as_asgi()),
]

application = ProtocolTypeRouter({
    'websocket': AllowedHostsOriginValidator(  # Security: validate origin
        JWTAuthMiddleware(
            URLRouter(websocket_urlpatterns)
        )
    ),
})