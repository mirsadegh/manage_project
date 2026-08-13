from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    NotificationViewSet,
    NotificationPreferenceViewSet,
    NotificationTemplateViewSet,
)

router = DefaultRouter()
router.register(
    r'preferences', NotificationPreferenceViewSet, basename='notification-preference'
)
router.register(
    r'templates', NotificationTemplateViewSet, basename='notification-template'
)
router.register(r'', NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]
