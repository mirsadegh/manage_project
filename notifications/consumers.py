# notifications/consumers.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

User = get_user_model()

class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time notifications.
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope['user']
        
        if self.user.is_authenticated:
            # Create user-specific channel group
            self.group_name = f'user_{self.user.id}_notifications'
            
            # Join group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            await self.accept()
            
            # Send connection confirmation
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': 'Connected to notifications'
            }))
        else:
            await self.close()
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        if self.user.is_authenticated:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Handle messages from WebSocket"""
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'mark_read':
            notification_id = data.get('notification_id')
            await self.mark_notification_read(notification_id)
    
    async def notification_message(self, event):
        """Send notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'notification': event['notification']
        }))
    
    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        """Mark notification as read"""
        from .models import Notification
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=self.user
            )
            notification.mark_as_read()
        except Notification.DoesNotExist:
            pass


class ProjectConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time project updates.
    """
    
    async def connect(self):
        """Handle WebSocket connection"""
        self.user = self.scope['user']
        self.project_slug = self.scope['url_route']['kwargs']['project_slug']
        self.group_name = f'project_{self.project_slug}'
        
        if self.user.is_authenticated:
            # Check if user has access to project
            has_access = await self.check_project_access()
            
            if has_access:
                await self.channel_layer.group_add(
                    self.group_name,
                    self.channel_name
                )
                await self.accept()
            else:
                await self.close()
        else:
            await self.close()
    
    async def disconnect(self, close_code):
        """Handle disconnection"""
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
    
    async def receive(self, text_data):
        """Handle incoming messages"""
        data = json.dumps(text_data)
        message_type = data.get('type')
        
        # Handle different message types
        if message_type == 'task_update':
            await self.handle_task_update(data)
    
    # async def task_update