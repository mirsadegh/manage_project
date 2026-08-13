

from django.urls import path
from . import consumers
from projects.consumers import ProjectConsumer

websocket_urlpatterns = [
    path('ws/notifications/', consumers.NotificationConsumer.as_asgi()),
    path('ws/projects/<slug:project_slug>/', ProjectConsumer.as_asgi()),
]