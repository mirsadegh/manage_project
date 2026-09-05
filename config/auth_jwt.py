"""
Cookie-aware JWT authentication for DRF.

PR-6 made HttpOnly cookies the source of truth for the React frontend
(`ws_access` for the access token, `ws_refresh` for the refresh token).
Stock `rest_framework_simplejwt.authentication.JWTAuthentication` only
reads the `Authorization: Bearer <token>` header, so once the browser
stopped sending that header, every authenticated HTTP endpoint began
returning 401 even though the cookie was correctly attached.

This module adds `CookieJWTAuthentication`, which:

  1. Tries the Authorization header first (so existing API clients,
     curl scripts, server-to-server callers, and test fixtures that
     sign their requests with a header keep working unchanged).
  2. Falls back to the `ws_access` HttpOnly cookie.
  3. Re-validates the token via the parent class (signature, exp,
     token type).
  4. Adds a blacklist check on top of the parent class — the stock
     `JWTAuthentication.get_validated_token` only checks JWT claims
     and does NOT consult the `BlacklistedToken` table. Without this
     step, a token that has been revoked by `/accounts/auth/logout/`
     (with `logout_all=True`) would still be accepted for HTTP
     requests, breaking the "logout everywhere" guarantee that
     `LogoutView` and `_blacklist_user_tokens` rely on.

Blacklist enforcement matches what `config/websocket_auth.py` does on
the WebSocket path so HTTP and WS see the same authentication state.
"""
from __future__ import annotations

from typing import Optional, Tuple

from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import Token

from .auth_cookies import ACCESS_COOKIE


class CookieJWTAuthentication(JWTAuthentication):
    """DRF authentication class that accepts the JWT from either the
    `Authorization: Bearer <token>` header or the `ws_access` HttpOnly
    cookie, and that enforces the SimpleJWT blacklist on every request.
    """

    # Re-declare for clarity. Matches SimpleJWT defaults but is set
    # here so future maintainers don't have to dig through the parent
    # class to find out what header we read.
    www_authenticate_realm = "api"
    media_type = "application/json"

    def authenticate(self, request: Request) -> Optional[Tuple]:
        """Resolve the request's user from header or cookie.

        Returns a `(user, validated_token)` tuple on success and `None`
        when no credentials are present. Raises
        `rest_framework_simplejwt.exceptions.InvalidToken` only when
        credentials ARE present but invalid (so DRF surfaces a 401
        instead of a 403, which is the correct signal for bad auth).
        """
        # 1. Authorization header (backwards compat / API tools).
        #    The parent's `get_header` and `get_raw_token` are tolerant
        #    of absent / malformed headers and return None in that
        #    case, so this is a safe first attempt.
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is not None:
                validated_token = self.get_validated_token(raw_token)
                return self.get_user(validated_token), validated_token

        # 2. HttpOnly cookie (the PR-6 path for browser SPAs).
        raw_token = request.COOKIES.get(ACCESS_COOKIE)
        if not raw_token:
            # No credentials anywhere → DRF will fall through to
            # permission classes, which return 401/403 as appropriate.
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token

    def get_validated_token(self, raw_token: bytes | str) -> Token:
        """Validate the token AND enforce the blacklist.

        The parent class only checks signature, expiry, and token type.
        We additionally look up the `jti` claim in the
        `BlacklistedToken` table and raise `InvalidToken` if found.
        That keeps the HTTP and WebSocket auth surfaces in sync:
        `_blacklist_user_tokens()` (called by `LogoutView` with
        `logout_all=True`, by `change_password`, by `deactivate_account`,
        and by the password-reset-confirm flow) revokes tokens for
        BOTH paths, not just WS.
        """
        # Local import to avoid importing the blacklist app at module
        # import time (the rest of config.auth_jwt only needs the
        # auth helpers).
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

        validated_token = super().get_validated_token(raw_token)

        jti = validated_token.get("jti")
        if jti and BlacklistedToken.objects.filter(token__jti=jti).exists():
            raise InvalidToken("Token is blacklisted")

        return validated_token
