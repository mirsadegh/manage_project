from rest_framework.pagination import PageNumberPagination, LimitOffsetPagination, CursorPagination
from rest_framework.response import Response
from collections import OrderedDict

class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination with 20 items per page.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('results', data)
        ]))


class LargeResultsSetPagination(PageNumberPagination):
    """
    Pagination for large datasets with 100 items per page.
    """
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000


class SmallResultsSetPagination(PageNumberPagination):
    """
    Pagination for small datasets with 10 items per page.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class ProjectPagination(PageNumberPagination):
    """
    Custom pagination for projects.
    """
    page_size = 15
    page_size_query_param = 'page_size'
    max_page_size = 50
    
    def get_paginated_response(self, data):
        return Response({
            'pagination': {
                'count': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'page_size': self.page_size,
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            },
            'projects': data
        })


class TaskPagination(PageNumberPagination):
    """
    Custom pagination for tasks with metadata.
    """
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        # Calculate task statistics using single aggregation query for better performance
        from tasks.models import Task
        from django.db.models import Count, Q

        stats = Task.objects.aggregate(
            total_tasks=Count('id'),
            completed_tasks=Count('id', filter=Q(status='COMPLETED')),
            in_progress_tasks=Count('id', filter=Q(status='IN_PROGRESS')),
            todo_tasks=Count('id', filter=Q(status='TODO')),
        )

        return Response({
            'pagination': {
                'count': self.page.paginator.count,
                'total_pages': self.page.paginator.num_pages,
                'current_page': self.page.number,
                'page_size': self.page_size,
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
            },
            'statistics': stats,
            'tasks': data
        })


class CustomLimitOffsetPagination(LimitOffsetPagination):
    """
    Limit/Offset pagination for flexible control.
    Usage: ?limit=10&offset=20
    """
    default_limit = 20
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    max_limit = 100


class ActivityLogPagination(CursorPagination):
    """
    Cursor-based pagination for activity logs (best for real-time feeds).
    """
    page_size = 50
    ordering = '-created_at'
    cursor_query_param = 'cursor'

