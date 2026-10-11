"""Shared helpers used across accounts.views submodules."""
import logging

from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from django.contrib.auth import get_user_model

User = get_user_model()

logger = logging.getLogger('accounts')


def _blacklist_user_tokens(user):
    """Helper — blacklist all outstanding refresh tokens for a user.

    Called on password change, password reset, and account deactivation
    so other-device sessions are forced to re-authenticate. Errors on
    individual rows are swallowed (best-effort) so a single bad row
    cannot block the call.
    """
    for token in OutstandingToken.objects.filter(user=user):
        try:
            BlacklistedToken.objects.get_or_create(token=token)
        except Exception:
            logger.exception("failed to blacklist token id=%s for user_id=%s", token.id, user.id)
