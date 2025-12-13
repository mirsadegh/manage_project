# notifications/consumers.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

User = get_user_model()


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time user notifications.
    URL: ws://localhost:8000/ws/notifications/
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope['user']
        
        if self.user.is_authenticated:
            # Create unique group name for this user
            self.group_name = f'user_{self.user.id}_notifications'
            
            # Add this channel to the user's group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            # Accept the connection
            await self.accept()
            
            # Send confirmation message
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': f'Connected to notifications for {self.user.username}'
            }))
        else:
            # Reject unauthenticated connections
            await self.close()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        if self.user.is_authenticated:
            # Remove this channel from the user's group
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """
        Handle messages received from WebSocket client.
        Client can send: {"type": "mark_read", "notification_id": 123}
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'mark_read':
                notification_id = data.get('notification_id')
                await self.mark_notification_read(notification_id)
                
                # Send confirmation back to client
                await self.send(text_data=json.dumps({
                    'type': 'notification_marked_read',
                    'notification_id': notification_id
                }))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
    
    async def notification_message(self, event):
        """
        Handle notification messages sent to this group.
        This is called by send_realtime_notification() utility.
        """
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'notification': event['notification']
        }))
    
    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        """Mark a notification as read in the database"""
        from .models import Notification
        
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=self.user
            )
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False


class ProjectConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time project updates.
    URL: ws://localhost:8000/ws/projects/<slug>/
    """
    
    async def connect(self):
        """Handle WebSocket connection to a project"""
        self.user = self.scope['user']
        self.project_slug = self.scope['url_route']['kwargs']['project_slug']
        self.group_name = f'project_{self.project_slug}'
        
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Check if user has access to this project
        has_access = await self.check_project_access()
        
        if has_access:
            # Add to project group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            await self.accept()
            
            # Send confirmation
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': f'Connected to project: {self.project_slug}'
            }))
        else:
            # User doesn't have access
            await self.close(code=4003)
    
    async def disconnect(self, close_code):
        """Handle disconnection from project"""
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Handle incoming messages from client"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            # Handle different message types
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong'
                }))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
    
    async def task_update(self, event):
        """
        Send task update to all project members.
        Called by broadcast_project_update() utility.
        """
        await self.send(text_data=json.dumps({
            'type': 'task_update',
            'data': event['task']
        }))
    
    async def project_update(self, event):
        """Send project update to all members"""
        await self.send(text_data=json.dumps({
            'type': 'project_update',
            'data': event['project']
        }))
    
    async def member_joined(self, event):
        """Notify when a new member joins the project"""
        await self.send(text_data=json.dumps({
            'type': 'member_joined',
            'data': event['member']
        }))
    
    @database_sync_to_async
    def check_project_access(self):
        """Check if user has permission to access this project"""
        from projects.models import Project, ProjectMember
        
        try:
            project = Project.objects.get(slug=self.project_slug)
            
            # Check various access conditions
            is_owner = project.owner == self.user
            is_manager = project.manager == self.user
            is_member = ProjectMember.objects.filter(
                project=project,
                user=self.user
            ).exists()
            is_public = project.is_public
            
            return is_owner or is_manager or is_member or is_public
            
        except Project.DoesNotExist:
            return False