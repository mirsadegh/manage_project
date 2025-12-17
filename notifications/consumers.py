import json
import logging
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

User = get_user_model()
logger = logging.getLogger(__name__)


class BaseConsumer(AsyncWebsocketConsumer):
    """
    Base consumer with common functionality for all WebSocket consumers.
    """
    
    # Configuration
    HEARTBEAT_INTERVAL = 30  # seconds
    CONNECTION_TIMEOUT = 300  # 5 minutes without activity
    
    async def send_json(self, data):
        """Helper method to send JSON data."""
        await self.send(text_data=json.dumps(data, default=str))
    
    async def send_error(self, message, code=None):
        """Send error message to client."""
        error_data = {
            'type': 'error',
            'message': message,
            'timestamp': timezone.now().isoformat(),
        }
        if code:
            error_data['code'] = code
        await self.send_json(error_data)
    
    async def send_success(self, message, data=None):
        """Send success message to client."""
        response = {
            'type': 'success',
            'message': message,
            'timestamp': timezone.now().isoformat(),
        }
        if data:
            response['data'] = data
        await self.send_json(response)
    
    def get_client_ip(self):
        """Extract client IP from scope."""
        headers = dict(self.scope.get('headers', []))
        x_forwarded_for = headers.get(b'x-forwarded-for', b'').decode()
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        client = self.scope.get('client')
        return client[0] if client else 'unknown'


class NotificationConsumer(BaseConsumer):
    """
    WebSocket consumer for real-time user notifications.
    
    URL: ws://localhost:8000/ws/notifications/?token=<jwt_token>
    
    Client can send:
        - {"type": "ping"} - Heartbeat
        - {"type": "mark_read", "notification_id": 123}
        - {"type": "mark_all_read"}
        - {"type": "get_unread_count"}
        - {"type": "get_recent", "limit": 10}
        - {"type": "subscribe_categories", "categories": ["task", "project"]}
    
    Server sends:
        - {"type": "connection_established", ...}
        - {"type": "notification", "notification": {...}}
        - {"type": "unread_count", "count": 5}
        - {"type": "notification_marked_read", "notification_id": 123}
        - {"type": "pong"}
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_name = None
        self.subscribed_categories = set()
        self.connected_at = None
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.user = self.scope.get('user')
        
        # Check authentication
        if not self.user or not self.user.is_authenticated:
            auth_error = self.scope.get('auth_error', 'Authentication required')
            logger.warning(
                f"Notification WebSocket rejected from {self.get_client_ip()}: {auth_error}"
            )
            await self.close(code=4001)
            return
        
        # Setup user's notification group
        self.group_name = f'user_{self.user.id}_notifications'
        self.connected_at = timezone.now()
        
        # Join notification group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        # Track connection
        await self._track_connection(connected=True)
        
        # Accept connection
        await self.accept()
        
        # Send connection confirmation with initial data
        unread_count = await self._get_unread_count()
        recent_notifications = await self._get_recent_notifications(limit=5)
        
        await self.send_json({
            'type': 'connection_established',
            'message': f'Connected to notifications',
            'user': {
                'id': self.user.id,
                'username': self.user.username,
            },
            'unread_count': unread_count,
            'recent_notifications': recent_notifications,
            'timestamp': timezone.now().isoformat(),
        })
        
        logger.info(f"User {self.user.username} connected to notifications")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if self.group_name:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        
        if hasattr(self, 'user') and self.user and self.user.is_authenticated:
            await self._track_connection(connected=False)
            duration = (timezone.now() - self.connected_at).seconds if self.connected_at else 0
            logger.info(
                f"User {self.user.username} disconnected from notifications "
                f"(code: {close_code}, duration: {duration}s)"
            )
    
    async def receive(self, text_data):
        """Handle messages received from WebSocket client."""
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error('Invalid JSON format', code='INVALID_JSON')
            return
        
        message_type = data.get('type', '')
        
        # Map message types to handlers
        handlers = {
            'ping': self._handle_ping,
            'mark_read': self._handle_mark_read,
            'mark_all_read': self._handle_mark_all_read,
            'get_unread_count': self._handle_get_unread_count,
            'get_recent': self._handle_get_recent,
            'subscribe_categories': self._handle_subscribe_categories,
            'unsubscribe_categories': self._handle_unsubscribe_categories,
            'delete_notification': self._handle_delete_notification,
        }
        
        handler = handlers.get(message_type)
        if handler:
            try:
                await handler(data)
            except Exception as e:
                logger.error(f"Error handling {message_type}: {e}")
                await self.send_error(f'Error processing {message_type}', code='HANDLER_ERROR')
        else:
            await self.send_error(f'Unknown message type: {message_type}', code='UNKNOWN_TYPE')
    
    # Message handlers
    async def _handle_ping(self, data):
        """Respond to ping with pong (heartbeat)."""
        await self.send_json({
            'type': 'pong',
            'timestamp': data.get('timestamp'),
            'server_time': timezone.now().isoformat(),
        })
    
    async def _handle_mark_read(self, data):
        """Mark a specific notification as read."""
        notification_id = data.get('notification_id')
        
        if not notification_id:
            await self.send_error('notification_id is required', code='MISSING_PARAM')
            return
        
        success = await self._mark_notification_read(notification_id)
        
        if success:
            unread_count = await self._get_unread_count()
            await self.send_json({
                'type': 'notification_marked_read',
                'notification_id': notification_id,
                'unread_count': unread_count,
            })
        else:
            await self.send_error('Notification not found', code='NOT_FOUND')
    
    async def _handle_mark_all_read(self, data):
        """Mark all notifications as read."""
        category = data.get('category')  # Optional: only mark specific category
        count = await self._mark_all_notifications_read(category=category)
        
        await self.send_json({
            'type': 'all_notifications_marked_read',
            'marked_count': count,
            'category': category,
            'unread_count': 0 if not category else await self._get_unread_count(),
        })
    
    async def _handle_get_unread_count(self, data):
        """Get current unread notification count."""
        category = data.get('category')
        count = await self._get_unread_count(category=category)
        
        await self.send_json({
            'type': 'unread_count',
            'count': count,
            'category': category,
        })
    
    async def _handle_get_recent(self, data):
        """Get recent notifications."""
        limit = min(data.get('limit', 10), 50)  # Cap at 50
        offset = data.get('offset', 0)
        category = data.get('category')
        unread_only = data.get('unread_only', False)
        
        notifications = await self._get_recent_notifications(
            limit=limit,
            offset=offset,
            category=category,
            unread_only=unread_only
        )
        
        await self.send_json({
            'type': 'recent_notifications',
            'notifications': notifications,
            'limit': limit,
            'offset': offset,
            'category': category,
        })
    
    async def _handle_subscribe_categories(self, data):
        """Subscribe to specific notification categories."""
        categories = data.get('categories', [])
        if isinstance(categories, list):
            self.subscribed_categories.update(categories)
            await self.send_json({
                'type': 'subscribed',
                'categories': list(self.subscribed_categories),
            })
    
    async def _handle_unsubscribe_categories(self, data):
        """Unsubscribe from specific notification categories."""
        categories = data.get('categories', [])
        if isinstance(categories, list):
            self.subscribed_categories.difference_update(categories)
            await self.send_json({
                'type': 'unsubscribed',
                'categories': list(self.subscribed_categories),
            })
    
    async def _handle_delete_notification(self, data):
        """Delete a notification."""
        notification_id = data.get('notification_id')
        
        if not notification_id:
            await self.send_error('notification_id is required', code='MISSING_PARAM')
            return
        
        success = await self._delete_notification(notification_id)
        
        if success:
            await self.send_json({
                'type': 'notification_deleted',
                'notification_id': notification_id,
            })
        else:
            await self.send_error('Notification not found', code='NOT_FOUND')
    
    # Channel layer event handlers (called from other parts of the app)
    async def notification_message(self, event):
        """Handle new notification event from channel layer."""
        notification = event.get('notification', {})
        
        # Check category filter if subscriptions are active
        if self.subscribed_categories:
            category = notification.get('category') or notification.get('notification_type')
            if category and category not in self.subscribed_categories:
                return
        
        await self.send_json({
            'type': 'notification',
            'notification': notification,
        })
    
    async def notification_update(self, event):
        """Handle notification update event."""
        await self.send_json({
            'type': 'notification_update',
            'notification_id': event.get('notification_id'),
            'data': event.get('data', {}),
        })
    
    async def unread_count_update(self, event):
        """Handle unread count update event."""
        await self.send_json({
            'type': 'unread_count',
            'count': event.get('count'),
        })
    
    async def bulk_notification(self, event):
        """Handle bulk notification event."""
        await self.send_json({
            'type': 'bulk_notification',
            'notifications': event.get('notifications', []),
            'count': event.get('count', 0),
        })
    
    # Database operations
    @database_sync_to_async
    def _get_unread_count(self, category=None):
        """Get unread notification count for user."""
        from notifications.models import Notification
        
        queryset = Notification.objects.filter(
            recipient=self.user,
            read=False
        )
        
        if category:
            queryset = queryset.filter(notification_type=category)
        
        return queryset.count()
    
    @database_sync_to_async
    def _get_recent_notifications(self, limit=10, offset=0, category=None, unread_only=False):
        """Get recent notifications for user."""
        from notifications.models import Notification
        
        queryset = Notification.objects.filter(recipient=self.user)
        
        if category:
            queryset = queryset.filter(notification_type=category)
        
        if unread_only:
            queryset = queryset.filter(read=False)
        
        notifications = queryset.order_by('-created_at')[offset:offset + limit]
        
        return [
            {
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'notification_type': n.notification_type,
                'read': n.read,
                'created_at': n.created_at.isoformat(),
                'data': n.data if hasattr(n, 'data') else {},
            }
            for n in notifications
        ]
    
    @database_sync_to_async
    def _mark_notification_read(self, notification_id):
        """Mark a notification as read in the database."""
        from notifications.models import Notification
        
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=self.user
            )
            if hasattr(notification, 'mark_as_read'):
                notification.mark_as_read()
            else:
                notification.read = True
                notification.read_at = timezone.now()
                notification.save(update_fields=['read', 'read_at'])
            return True
        except Notification.DoesNotExist:
            return False
    
    @database_sync_to_async
    def _mark_all_notifications_read(self, category=None):
        """Mark all user notifications as read."""
        from notifications.models import Notification
        
        queryset = Notification.objects.filter(
            recipient=self.user,
            read=False
        )
        
        if category:
            queryset = queryset.filter(notification_type=category)
        
        return queryset.update(read=True, read_at=timezone.now())
    
    @database_sync_to_async
    def _delete_notification(self, notification_id):
        """Delete a notification."""
        from notifications.models import Notification
        
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=self.user
            )
            notification.delete()
            return True
        except Notification.DoesNotExist:
            return False
    
    @database_sync_to_async
    def _track_connection(self, connected):
        """Track user's WebSocket connection status."""
        cache_key = f"ws_notifications_connected_{self.user.id}"
        if connected:
            current = cache.get(cache_key, 0)
            cache.set(cache_key, current + 1, 3600)
        else:
            current = cache.get(cache_key, 0)
            cache.set(cache_key, max(0, current - 1), 3600)


class ProjectConsumer(BaseConsumer):
    """
    WebSocket consumer for real-time project updates.
    
    URL: ws://localhost:8000/ws/projects/<slug>/?token=<jwt_token>
    
    Client can send:
        - {"type": "ping"} - Heartbeat
        - {"type": "typing_start", "field": "description"}
        - {"type": "typing_stop", "field": "description"}
        - {"type": "cursor_position", "position": {"x": 100, "y": 200}}
        - {"type": "get_online_users"}
        - {"type": "request_sync"} - Request full project state
    
    Server sends:
        - {"type": "connection_established", ...}
        - {"type": "user_joined", "user": {...}}
        - {"type": "user_left", "user": {...}}
        - {"type": "task_update", "data": {...}}
        - {"type": "project_update", "data": {...}}
        - {"type": "typing_indicator", ...}
        - {"type": "online_users", "users": [...]}
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_name = None
        self.project_slug = None
        self.project_id = None
        self.connected_at = None
    
    async def connect(self):
        """Handle WebSocket connection to a project."""
        self.user = self.scope.get('user')
        self.project_slug = self.scope['url_route']['kwargs'].get('project_slug')
        
        # Check authentication
        if not self.user or not self.user.is_authenticated:
            logger.warning(
                f"Project WebSocket rejected from {self.get_client_ip()}: Not authenticated"
            )
            await self.close(code=4001)
            return
        
        # Check project access
        project_info = await self._check_project_access()
        
        if not project_info:
            logger.warning(
                f"User {self.user.username} denied access to project {self.project_slug}"
            )
            await self.close(code=4003)
            return
        
        self.project_id = project_info['id']
        self.group_name = f'project_{self.project_slug}'
        self.connected_at = timezone.now()
        
        # Add to project group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        # Track online user
        await self._add_online_user()
        
        # Accept connection
        await self.accept()
        
        # Notify others that user joined
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'user_joined',
                'user': {
                    'id': self.user.id,
                    'username': self.user.username,
                    'full_name': self.user.get_full_name(),
                    'avatar': getattr(self.user, 'avatar_url', None),
                },
            }
        )
        
        # Send connection confirmation with initial data
        online_users = await self._get_online_users()
        project_summary = await self._get_project_summary()
        
        await self.send_json({
            'type': 'connection_established',
            'message': f'Connected to project: {self.project_slug}',
            'project': project_summary,
            'online_users': online_users,
            'user': {
                'id': self.user.id,
                'username': self.user.username,
                'role': project_info.get('role'),
            },
            'timestamp': timezone.now().isoformat(),
        })
        
        logger.info(f"User {self.user.username} joined project {self.project_slug}")
    
    async def disconnect(self, close_code):
        """Handle disconnection from project."""
        if self.group_name:
            # Notify others that user left
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'user_left',
                    'user': {
                        'id': self.user.id,
                        'username': self.user.username,
                    },
                }
            )
            
            # Remove from group
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        
        if hasattr(self, 'user') and self.user and self.user.is_authenticated:
            await self._remove_online_user()
            duration = (timezone.now() - self.connected_at).seconds if self.connected_at else 0
            logger.info(
                f"User {self.user.username} left project {self.project_slug} "
                f"(code: {close_code}, duration: {duration}s)"
            )
    
    async def receive(self, text_data):
        """Handle incoming messages from client."""
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error('Invalid JSON format', code='INVALID_JSON')
            return
        
        message_type = data.get('type', '')
        
        handlers = {
            'ping': self._handle_ping,
            'typing_start': self._handle_typing_start,
            'typing_stop': self._handle_typing_stop,
            'cursor_position': self._handle_cursor_position,
            'get_online_users': self._handle_get_online_users,
            'request_sync': self._handle_request_sync,
            'focus_task': self._handle_focus_task,
            'unfocus_task': self._handle_unfocus_task,
        }
        
        handler = handlers.get(message_type)
        if handler:
            try:
                await handler(data)
            except Exception as e:
                logger.error(f"Error handling {message_type}: {e}")
                await self.send_error(f'Error processing {message_type}', code='HANDLER_ERROR')
        else:
            await self.send_error(f'Unknown message type: {message_type}', code='UNKNOWN_TYPE')
    
    # Message handlers
    async def _handle_ping(self, data):
        """Respond to ping."""
        await self.send_json({
            'type': 'pong',
            'timestamp': data.get('timestamp'),
            'server_time': timezone.now().isoformat(),
        })
    
    async def _handle_typing_start(self, data):
        """Broadcast typing indicator start."""
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'typing_indicator',
                'user_id': self.user.id,
                'username': self.user.username,
                'is_typing': True,
                'field': data.get('field'),
                'task_id': data.get('task_id'),
            }
        )
    
    async def _handle_typing_stop(self, data):
        """Broadcast typing indicator stop."""
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'typing_indicator',
                'user_id': self.user.id,
                'username': self.user.username,
                'is_typing': False,
                'field': data.get('field'),
                'task_id': data.get('task_id'),
            }
        )
    
    async def _handle_cursor_position(self, data):
        """Broadcast cursor position for collaborative editing."""
        position = data.get('position')
        if position:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'cursor_update',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'position': position,
                    'element_id': data.get('element_id'),
                }
            )
    
    async def _handle_get_online_users(self, data):
        """Get list of online users in this project."""
        online_users = await self._get_online_users()
        await self.send_json({
            'type': 'online_users',
            'users': online_users,
        })
    
    async def _handle_request_sync(self, data):
        """Request full project state sync."""
        project_data = await self._get_full_project_data()
        await self.send_json({
            'type': 'sync_response',
            'project': project_data,
            'timestamp': timezone.now().isoformat(),
        })
    
    async def _handle_focus_task(self, data):
        """Notify others that user is viewing/editing a task."""
        task_id = data.get('task_id')
        if task_id:
            await self._set_user_focus(task_id)
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'user_focus',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'task_id': task_id,
                    'action': 'focus',
                }
            )
    
    async def _handle_unfocus_task(self, data):
        """Notify others that user stopped viewing/editing a task."""
        task_id = data.get('task_id')
        await self._clear_user_focus()
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'user_focus',
                'user_id': self.user.id,
                'username': self.user.username,
                'task_id': task_id,
                'action': 'unfocus',
            }
        )
    
    # Channel layer event handlers
    async def user_joined(self, event):
        """Handle user joined event."""
        if event['user']['id'] != self.user.id:
            await self.send_json({
                'type': 'user_joined',
                'user': event['user'],
            })
    
    async def user_left(self, event):
        """Handle user left event."""
        if event['user']['id'] != self.user.id:
            await self.send_json({
                'type': 'user_left',
                'user': event['user'],
            })
    
    async def typing_indicator(self, event):
        """Handle typing indicator event."""
        if event['user_id'] != self.user.id:
            await self.send_json({
                'type': 'typing_indicator',
                'user_id': event['user_id'],
                'username': event['username'],
                'is_typing': event['is_typing'],
                'field': event.get('field'),
                'task_id': event.get('task_id'),
            })
    
    async def cursor_update(self, event):
        """Handle cursor update event."""
        if event['user_id'] != self.user.id:
            await self.send_json({
                'type': 'cursor_update',
                'user_id': event['user_id'],
                'username': event['username'],
                'position': event['position'],
                'element_id': event.get('element_id'),
            })
    
    async def user_focus(self, event):
        """Handle user focus event."""
        if event['user_id'] != self.user.id:
            await self.send_json(event)
    
    async def task_update(self, event):
        """Send task update to client."""
        await self.send_json({
            'type': 'task_update',
            'action': event.get('action', 'update'),
            'task': event.get('task') or event.get('data'),
            'updated_by': event.get('updated_by'),
        })
    
    async def task_created(self, event):
        """Handle new task created event."""
        await self.send_json({
            'type': 'task_created',
            'task': event['task'],
            'created_by': event.get('created_by'),
        })
    
    async def task_deleted(self, event):
        """Handle task deleted event."""
        await self.send_json({
            'type': 'task_deleted',
            'task_id': event['task_id'],
            'deleted_by': event.get('deleted_by'),
        })
    
    async def project_update(self, event):
        """Send project update to client."""
        await self.send_json({
            'type': 'project_update',
            'data': event.get('project') or event.get('data'),
            'updated_by': event.get('updated_by'),
        })
    
    async def member_joined(self, event):
        """Notify when a new member joins the project."""
        await self.send_json({
            'type': 'member_joined',
            'member': event['member'],
        })
    
    async def member_left(self, event):
        """Notify when a member leaves the project."""
        await self.send_json({
            'type': 'member_left',
            'member': event['member'],
        })
    
    async def comment_added(self, event):
        """Handle new comment event."""
        await self.send_json({
            'type': 'comment_added',
            'comment': event['comment'],
            'task_id': event.get('task_id'),
        })
    
    # Database operations
    @database_sync_to_async
    def _check_project_access(self):
        """Check if user has permission to access this project."""
        from projects.models import Project, ProjectMember
        
        try:
            project = Project.objects.get(slug=self.project_slug)
            
            is_owner = project.owner == self.user
            is_manager = getattr(project, 'manager', None) == self.user
            
            member = ProjectMember.objects.filter(
                project=project,
                user=self.user
            ).first()
            
            is_member = member is not None
            is_public = getattr(project, 'is_public', False)
            is_admin = self.user.role in ['admin', 'manager'] if hasattr(self.user, 'role') else False
            
            if is_owner or is_manager or is_member or is_public or is_admin:
                role = 'owner' if is_owner else (
                    'manager' if is_manager else (
                        member.role if member else 'viewer'
                    )
                )
                return {
                    'id': project.id,
                    'role': role,
                    'can_edit': role in ['owner', 'manager', 'editor', 'admin'],
                }
            
            return None
            
        except Project.DoesNotExist:
            return None
    
    @database_sync_to_async
    def _get_project_summary(self):
        """Get project summary data."""
        from projects.models import Project
        
        try:
            project = Project.objects.get(slug=self.project_slug)
            return {
                'id': project.id,
                'name': project.name,
                'slug': project.slug,
                'status': getattr(project, 'status', None),
                'task_count': project.tasks.count() if hasattr(project, 'tasks') else 0,
            }
        except Project.DoesNotExist:
            return {}
    
    @database_sync_to_async
    def _get_full_project_data(self):
        """Get full project data for sync."""
        from projects.models import Project
        
        try:
            project = Project.objects.prefetch_related('tasks', 'members').get(
                slug=self.project_slug
            )
            
            tasks = []
            if hasattr(project, 'tasks'):
                tasks = [
                    {
                        'id': t.id,
                        'title': t.title,
                        'status': t.status,
                        'priority': getattr(t, 'priority', None),
                        'assignee_id': getattr(t, 'assignee_id', None),
                    }
                    for t in project.tasks.all()[:100]  # Limit for performance
                ]
            
            return {
                'id': project.id,
                'name': project.name,
                'slug': project.slug,
                'description': getattr(project, 'description', ''),
                'status': getattr(project, 'status', None),
                'tasks': tasks,
            }
        except Project.DoesNotExist:
            return {}
    
    @database_sync_to_async
    def _get_online_users(self):
        """Get list of online users in this project."""
        cache_key = f"project_online_{self.project_slug}"
        online_users = cache.get(cache_key, {})
        return list(online_users.values())
    
    @database_sync_to_async
    def _add_online_user(self):
        """Add current user to online users list."""
        cache_key = f"project_online_{self.project_slug}"
        online_users = cache.get(cache_key, {})
        online_users[str(self.user.id)] = {
            'id': self.user.id,
            'username': self.user.username,
            'full_name': self.user.get_full_name(),
        }
        cache.set(cache_key, online_users, 3600)
    
    @database_sync_to_async
    def _remove_online_user(self):
        """Remove current user from online users list."""
        cache_key = f"project_online_{self.project_slug}"
        online_users = cache.get(cache_key, {})
        online_users.pop(str(self.user.id), None)
        cache.set(cache_key, online_users, 3600)
    
    @database_sync_to_async
    def _set_user_focus(self, task_id):
        """Set the task the user is currently focused on."""
        cache_key = f"project_focus_{self.project_slug}"
        focus_map = cache.get(cache_key, {})
        focus_map[str(self.user.id)] = task_id
        cache.set(cache_key, focus_map, 3600)
    
    @database_sync_to_async
    def _clear_user_focus(self):
        """Clear user's task focus."""
        cache_key = f"project_focus_{self.project_slug}"
        focus_map = cache.get(cache_key, {})
        focus_map.pop(str(self.user.id), None)
        cache.set(cache_key, focus_map, 3600)