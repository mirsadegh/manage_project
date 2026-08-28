# accounts/signals.py

"""
PR-3 Fix #1: bridge JWT token blacklist → WebSocket connection teardown.

When a BlacklistedToken row is created (i.e. a logout / revoke), we:
  1. publish a `force_disconnect` event to the user's WS control group so
     every live notification/project WebSocket closes itself with 4001;
  2. flush the cached `ws_token_*` entries for that user so subsequent
     connect attempts don't get a 5-minute-stale user from cache.

Wired in accounts.apps.AccountsConfig.ready().
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken


logger = logging.getLogger('accounts')


@receiver(post_save, sender=BlacklistedToken)
def force_disconnect_on_token_blacklist(sender, instance, created, **kwargs):
    if not created:
        # BlacklistedToken rows are immutable; updates don't happen.
        return

    user_id = instance.token.user_id
    if user_id is None:
        return

    # 1. Tell every live WS for this user to close.
    try:
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                f'user_{user_id}_ws_control',
                {'type': 'force_disconnect', 'reason': 'token_blacklisted'},
            )
    except Exception as exc:
        # Don't let a transient channel-layer failure block the blacklist save.
        logger.warning('Failed to publish force_disconnect for user %s: %s', user_id, exc)

    # 2. Flush cached token→user_id mappings. invalidate_user_token_cache
    # is @database_sync_to_async, so it must be wrapped to run sync here.
    try:
        from config.websocket_auth import invalidate_user_token_cache
        async_to_sync(invalidate_user_token_cache)(user_id)
    except Exception as exc:
        logger.warning('Failed to flush token cache for user %s: %s', user_id, exc)
