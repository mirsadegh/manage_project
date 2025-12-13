
from django.contrib import admin
from .models import Comment, CommentMention, CommentReaction


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'author', 'content_type', 'object_id', 'is_edited', 'created_at']
    list_filter = ['content_type', 'is_edited', 'created_at']
    search_fields = ['text', 'author__username']
    raw_id_fields = ['author', 'parent']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(CommentMention)
class CommentMentionAdmin(admin.ModelAdmin):
    list_display = ['id', 'comment', 'mentioned_user', 'created_at']
    list_filter = ['created_at']
    search_fields = ['mentioned_user__username']
    raw_id_fields = ['comment', 'mentioned_user']


@admin.register(CommentReaction)
class CommentReactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'comment', 'user', 'reaction_type', 'created_at']
    list_filter = ['reaction_type', 'created_at']
    search_fields = ['user__username']
    raw_id_fields = ['comment', 'user']