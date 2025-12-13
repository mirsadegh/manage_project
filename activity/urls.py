from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ActivityLogViewSet, ActivityFeedViewSet

router = DefaultRouter()
router.register(r'activity-logs', ActivityLogViewSet, basename='activity-log')
router.register(r'activity-feed', ActivityFeedViewSet, basename='activity-feed')

urlpatterns = [
    path('', include(router.urls)),
]