# comments/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.contenttypes.models import ContentType
from .models import Comment, CommentReaction
from .serializers import CommentSerializer, CommentCreateSerializer, CommentReactionSerializer
from .permissions import IsCommentAuthorOrReadOnly, CanAccessProjectComments
import re


class CommentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for comments.
    
    Endpoints:
    - GET /comments/ - List all comments (filtered)
    - POST /comments/ - Create a comment
    - GET /comments/{id}/ - Get comment detail
    - PUT/PATCH /comments/{id}/ - Update comment
    - DELETE /comments/{id}/ - Delete comment
    - POST /comments/{id}/react/ - Add reaction
    - DELETE /comments/{id}/react/ - Remove reaction
    """
    
    queryset = Comment.objects.all()
    permission_classes = [IsAuthenticated, IsCommentAuthorOrReadOnly]
    
    def get_permissions(self):
        # Edit/delete must be restricted to the comment's author (or an admin),
        # not just any project member. List/retrieve/create/react only require
        # project membership via CanAccessProjectComments.
        if self.action in ('update', 'partial_update', 'destroy'):
            permission_classes = [
                IsAuthenticated,
                CanAccessProjectComments,
                IsCommentAuthorOrReadOnly,
            ]
        else:
            permission_classes = [IsAuthenticated, CanAccessProjectComments]

        return [permission() for permission in permission_classes]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CommentCreateSerializer
        return CommentSerializer
    
    def get_queryset(self):
           """Filter comments based on query parameters"""
           queryset = Comment.objects.select_related('author', 'parent').prefetch_related('replies', 'reactions')

           # Filter by content type and object
           content_type = self.request.query_params.get('content_type')
           object_id = self.request.query_params.get('object_id')

           if content_type:
               try:
                   ct = ContentType.objects.get(model=content_type.lower())
                   queryset = queryset.filter(content_type=ct)
                   if object_id:
                       queryset = queryset.filter(object_id=object_id)
               except ContentType.DoesNotExist:
                   queryset = queryset.none()
           else:
               # BOLA fix: no object filter => only comments on projects the
               # requester can access.
               queryset = self._scope_to_accessible_projects(queryset)

           # Filter top-level comments only (exclude replies)
           if self.request.query_params.get('top_level') == 'true':
               queryset = queryset.filter(parent__isnull=True)

           return queryset

    def _scope_to_accessible_projects(self, queryset):
        """Restrict to comments whose project/task the user can access."""
        from django.db.models import Q
        from projects.models import Project
        from tasks.models import Task

        user = self.request.user
        if user.is_superuser or getattr(user, 'role', None) in ['ADMIN', 'PM']:
            return queryset

        project_ids = list(
            Project.objects.filter(
                Q(owner=user) | Q(manager=user) |
                Q(members__user=user, members__is_active=True)
            ).values_list('id', flat=True)
        )
        project_ct = ContentType.objects.get(app_label='projects', model='project')
        task_ct = ContentType.objects.get(app_label='tasks', model='task')
        task_ids = list(
            Task.objects.filter(project_id__in=project_ids).values_list('id', flat=True)
        )
        return queryset.filter(
            Q(content_type=project_ct, object_id__in=project_ids) |
            Q(content_type=task_ct, object_id__in=task_ids)
        )

    
    
    def perform_create(self, serializer):
        """Create comment and process mentions"""
        comment = serializer.save(author=self.request.user)
        
        # Process @mentions in text
        self._process_mentions(comment)
        
        # Send notification to content owner
        self._notify_content_owner(comment)
    
    def perform_update(self, serializer):
        """Update comment and reprocess mentions"""
        comment = serializer.save()
        
        # Clear old mentions and reprocess
        comment.mentions.all().delete()
        self._process_mentions(comment)

    def destroy(self, request, *args, **kwargs):
        """Soft delete a comment."""
        comment = self.get_object()
        comment.is_deleted = True
        comment.text = '[This comment has been deleted]'
        comment.save(update_fields=['is_deleted', 'text', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=False, methods=['get'], url_path=r'statistics/(?P<object_type>[^/.]+)/(?P<object_id>\d+)')
    def statistics(self, request, object_type=None, object_id=None):
        """Get comment statistics for a content object"""
        from django.db.models import Count
        from tasks.models import Task

        object_type = object_type.lower()
        if object_type not in ('task', 'project'):
            return Response(
                {'error': 'Invalid object_type. Allowed: task, project'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
         # Authorization: must be a member of the related project.
        perm = CanAccessProjectComments()
        project = perm._get_project(object_type, object_id)
        if not perm._is_member(request.user, project):
            return Response(
                {'error': 'You do not have access to this content.'},
                status=status.HTTP_403_FORBIDDEN
            )    

        ct = ContentType.objects.get(model=object_type)

        if object_type == 'project':
            project_comments = Comment.objects.filter(
                content_type=ct, object_id=object_id
            )
            task_ids = Task.objects.filter(project_id=object_id).values_list('id', flat=True)
            task_ct = ContentType.objects.get(model='task')
            task_comments = Comment.objects.filter(
                content_type=task_ct, object_id__in=list(task_ids)
            )
            queryset = project_comments | task_comments
        else:
            queryset = Comment.objects.filter(content_type=ct, object_id=object_id)

        total_comments = queryset.count()

        top_commenters = list(
            queryset
            .values('author__id', 'author__username', 'author__first_name', 'author__last_name')
            .annotate(comment_count=Count('id'))
            .order_by('-comment_count')[:5]
        )

        return Response({
            'object_type': object_type,
            'object_id': object_id,
            'total_comments': total_comments,
            'top_commenters': top_commenters,
        })

    @action(detail=True, methods=['get'])
    def reactions(self, request, pk=None):
        """Get all reactions for a comment"""
        comment = self.get_object()
        reactions = CommentReaction.objects.filter(comment=comment)
        serializer = CommentReactionSerializer(reactions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post', 'delete'])
    def react(self, request, pk=None):
        """Add, update or remove reaction to comment"""
        comment = self.get_object()

        if request.method == 'DELETE':
            reaction_type = request.data.get('reaction_type')
            filters = {
                'comment': comment,
                'user': request.user,
            }
            if reaction_type:
                filters['reaction_type'] = reaction_type
            deleted_count = CommentReaction.objects.filter(**filters).delete()[0]
            if deleted_count > 0:
                return Response(status=status.HTTP_204_NO_CONTENT)
            return Response(
                {'error': 'Reaction not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        reaction_type = request.data.get('reaction_type')
        
        if not reaction_type or reaction_type not in dict(CommentReaction.ReactionType.choices):
            return Response(
                {'error': 'Valid reaction_type required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create or update reaction
        reaction, created = CommentReaction.objects.update_or_create(
            comment=comment,
            user=request.user,
            defaults={'reaction_type': reaction_type}
        )
        
        serializer = CommentReactionSerializer(reaction)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['delete'])
    def unreact(self, request, pk=None):
        """Remove reaction from comment"""
        comment = self.get_object()
        reaction_type = request.data.get('reaction_type')
        
        deleted_count = CommentReaction.objects.filter(
            comment=comment,
            user=request.user,
            reaction_type=reaction_type if reaction_type else None
        ).delete()[0]
        
        if deleted_count > 0:
            return Response(status=status.HTTP_204_NO_CONTENT)
        
        return Response(
            {'error': 'Reaction not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    def _process_mentions(self, comment):
        """Process @username mentions in comment text"""
        from accounts.models import CustomUser
        from .models import CommentMention
        
        # Find all @username patterns
        mention_pattern = r'@(\w+)'
        usernames = re.findall(mention_pattern, comment.text)
        
        for username in set(usernames):  # Use set to avoid duplicates
            try:
                user = CustomUser.objects.get(username=username)
                
                # Create mention record (notification handled by signal)
                CommentMention.objects.get_or_create(
                    comment=comment,
                    mentioned_user=user,
                    defaults={'mentioned_by': self.request.user}
                )
            except CustomUser.DoesNotExist:
                pass
    
    def _notify_content_owner(self, comment):
        """Notify the owner of the content being commented on"""
        from notifications.models import Notification
        
        content_object = comment.content_object
        
        # Determine who to notify based on content type
        recipient = None
        if hasattr(content_object, 'assignee'):  # Task
            recipient = content_object.assignee
        elif hasattr(content_object, 'owner'):  # Project
            recipient = content_object.owner
        
        if recipient and recipient != comment.author:
            Notification.objects.create(
                recipient=recipient,
                notification_type='TASK_COMMENT',
                title='New Comment',
                message=f'{comment.author.get_full_name()} commented on {content_object}',
                content_object=comment
            )