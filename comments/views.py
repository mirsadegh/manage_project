# comments/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.contenttypes.models import ContentType
from .models import Comment, CommentReaction
from .serializers import CommentSerializer, CommentCreateSerializer, CommentReactionSerializer
from .permissions import IsCommentAuthorOrReadOnly
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
        
        if content_type and object_id:
            try:
                ct = ContentType.objects.get(model=content_type.lower())
                queryset = queryset.filter(content_type=ct, object_id=object_id)
            except ContentType.DoesNotExist:
                queryset = queryset.none()
        
        # Filter top-level comments only (exclude replies)
        if self.request.query_params.get('top_level') == 'true':
            queryset = queryset.filter(parent__isnull=True)
        
        return queryset
    
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
    
    @action(detail=True, methods=['post'])
    def react(self, request, pk=None):
        """Add or update reaction to comment"""
        comment = self.get_object()
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
        from notifications.models import Notification
        
        # Find all @username patterns
        mention_pattern = r'@(\w+)'
        usernames = re.findall(mention_pattern, comment.text)
        
        for username in set(usernames):  # Use set to avoid duplicates
            try:
                user = CustomUser.objects.get(username=username)
                
                # Create mention record
                from .models import CommentMention
                CommentMention.objects.get_or_create(
                    comment=comment,
                    mentioned_user=user
                )
                
                # Send notification
                if user != comment.author:
                    Notification.objects.create(
                        recipient=user,
                        notification_type='MENTION',
                        title='You were mentioned',
                        message=f'{comment.author.get_full_name()} mentioned you in a comment',
                        content_object=comment
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