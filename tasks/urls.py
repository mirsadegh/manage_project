from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskListViewSet, TaskViewSet, TaskLabelViewSet

router = DefaultRouter()
router.register(r'task-lists', TaskListViewSet, basename='tasklist')
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'labels', TaskLabelViewSet, basename='label')

urlpatterns = [
    path('', include(router.urls)),
]