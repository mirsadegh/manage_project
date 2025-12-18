from channels.generic.websocket import AsyncWebsocketConsumer
from notifications.consumers import BaseConsumer
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




