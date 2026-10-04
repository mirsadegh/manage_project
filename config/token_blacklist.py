"""
Shared access-token blacklist helpers for both HTTP and WebSocket auth.

SimpleJWT's OutstandingToken table only tracks refresh tokens. Access tokens
stay cryptographically valid until their TTL expires. On logout we write the
access token's jti to the Django cache with a TTL equal to its remaining
lifetime. The entry self-evicts exactly when the token stops being verifiable.

This module is intentionally free of imports from websocket_auth or auth_jwt
to avoid circular dependencies. Both surfaces import from here.
"""
from __future__ import annotations

import logging
import time

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def _blacklist_key(jti: str) -> str:
    """Cache key for a revoked access-token jti."""
    return f"ws_access_blacklist_{jti}"


def blacklist_access_token(token_string: str) -> bool:
    """Blacklist an access token in the cache for the rest of its lifetime.

    Called on logout. Extracts jti/exp and writes the jti to the cache
    with the token's remaining lifetime as TTL. A token whose payload
    cannot be decoded is skipped (returns False). A cache write failure
    is logged at ERROR and also returns False — the caller completes the
    HTTP response normally, and operations that depend on revocation
    (WS reconnect block) will not apply until the entry exists.

    Returns True on success, False on any failure.
    """
    # Local import to avoid pulling in SimpleJWT at module load time
    # for callers that only need the read-side helper.
    from rest_framework_simplejwt.tokens import AccessToken

    try:
        access_token = AccessToken(token_string)
    except Exception:
        logger.warning("access-token blacklist: undecodable token, skipping")
        return False

    jti = access_token.get("jti")
    if not jti:
        return False

    exp = access_token.get("exp")
    # TTL bounded to remaining lifetime, clamped to >=1s so the entry is
    # always written even for a token in its final second.
    if exp:
        ttl = max(1, int(exp - time.time()))
    else:
        ttl = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())

    try:
        cache.set(_blacklist_key(jti), "1", ttl)
        logger.info("blacklisted access token jti=%s… ttl=%ss", jti[:8], ttl)
        return True
    except Exception:
        # Cache write failure is ERROR: the caller thinks logout succeeded
        # but the access token is still valid. Log immediately so an
        # operator can alert and the user's session is not silently
        # extended beyond their expectation.
        logger.error(
            "access-token blacklist: cache.set failed for jti=%s… "
            "(logout may not have revoked the session)",
            jti[:8],
        )
        return False


def is_jti_blacklisted(jti: str) -> bool:
    """Return True if the jti is on the access-token blacklist.

    Fail-closed: empty jti returns True (unidentifiable tokens are not
    trusted). Cache errors return True with a warning log — an
    unavailable store means unavailable trust. Never raises.
    """
    if not jti:
        return True

    try:
        return bool(cache.get(_blacklist_key(jti)))
    except Exception as e:
        logger.warning(
            "access-token blacklist: cache.get failed (%s), failing closed",
            type(e).__name__,
        )
        return True
