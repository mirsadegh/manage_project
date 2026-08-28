# accounts/signals.py

"""
WS-side hooks for the accounts app.

PR-3 Fix #1: when a JWT is blacklisted, close all live WS connections for
that user (force_disconnect) and flush the cached token mappings.

PR-3 Fix #15: when a user is deactivated (is_active=False), do the same —
close live WS and flush caches.

Wired in accounts.apps.AccountsConfig.ready().
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken


logger = logging.getLogger('accounts')


def _close_user_sessions(user_id, reason):
    """Publish force_disconnect and flush token cache for the user."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                f'user_{user_id}_ws_control',
                {'type': 'force_disconnect', 'reason': reason},
            )
    except Exception as exc:
        logger.warning(
            'Failed to publish force_disconnect for user %s: %s', user_id, exc,
        )
    try:
        from config.websocket_auth import invalidate_user_token_cache
        async_to_sync(invalidate_user_token_cache)(user_id)
    except Exception as exc:
        logger.warning(
            'Failed to flush token cache for user %s: %s', user_id, exc,
        )


@receiver(post_save, sender=BlacklistedToken)
def force_disconnect_on_token_blacklist(sender, instance, created, **kwargs):
    if not created:
        return
    user_id = instance.token.user_id
    if user_id is None:
        return
    _close_user_sessions(user_id, reason='token_blacklisted')


@receiver(post_save, sender='accounts.CustomUser')
def flush_user_cache_on_deactivation(sender, instance, created, update_fields=None, **kwargs):
    """PR-3 Fix #15: when a user is deactivated, close all live WS
    connections and flush cached token entries.
    """
    if instance.is_active:
        return
    if update_fields is not None and 'is_active' not in update_fields:
        return
    user_id = instance.id
    if user_id is None:
        return
    _close_user_sessions(user_id, reason='user_deactivated')
