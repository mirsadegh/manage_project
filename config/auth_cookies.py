"""
Cookie-based JWT helpers.

This module provides utilities for setting and clearing HttpOnly cookies that
carry the SimpleJWT access and refresh tokens. Cookies are the preferred
auth channel for WebSocket connections because:

  * The browser automatically includes them on the WebSocket upgrade
    handshake, so clients do not have to embed the token in the URL
    (which leaks it to proxy logs, browser history, and referer headers).
  * HttpOnly + SameSite=Lax mitigates XSS-based token theft and CSRF.
  * Server-side `Secure` flag is applied in production (`DEBUG=False`)
    so cookies are never sent over plain HTTP.

Migration note (PR-6):
  The token-issuance endpoints (login, register, refresh) now also set
  these cookies. The token body is still returned in the JSON response
  so existing tools and tests that read the body continue to work.
  Clients are encouraged to drop localStorage-based token storage.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional, Tuple

from django.conf import settings


# Cookie names. Public so tests can assert on them.
ACCESS_COOKIE = "ws_access"
REFRESH_COOKIE = "ws_refresh"


def _cookie_secure() -> bool:
    """Secure flag is True in production (HTTPS-only) and False in dev.

    This matches the policy already in place for SESSION_COOKIE_SECURE
    and CSRF_COOKIE_SECURE in `settings.py`.
    """
    return not settings.DEBUG


def _cookie_samesite() -> str:
    """SameSite=Lax protects against CSRF on cross-site POSTs while still
    allowing top-level navigations to carry the cookie. WebSocket
    connections on cross-origin sites are blocked by Lax, which is the
    desired behavior for a same-origin deployment.
    """
    return "Lax"


def set_auth_cookies(response, access: str, refresh: Optional[str] = None) -> None:
    """Attach the access (and optionally refresh) JWT as HttpOnly cookies.

    The cookie lifetime mirrors the SimpleJWT token lifetime so they
    expire together. The refresh cookie, if supplied, is also HttpOnly
    and uses the longer refresh-token TTL.
    """
    access_lifetime = int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=access,
        max_age=access_lifetime,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        path="/",
    )
    if refresh is not None:
        refresh_lifetime = int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
        response.set_cookie(
            key=REFRESH_COOKIE,
            value=refresh,
            max_age=refresh_lifetime,
            httponly=True,
            secure=_cookie_secure(),
            samesite=_cookie_samesite(),
            path="/",
        )


def clear_auth_cookies(response) -> None:
    """Remove the auth cookies from the client. Safe to call even if
    the cookies were never set.
    """
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


def _split_cookie_header(header: str) -> list[Tuple[str, str]]:
    """Parse a Cookie header into a list of (name, value) tuples.

    We avoid importing `http.cookies` because it lower-cases the names
    by default and we want exact-name matches so we do not collide
    with `csrftoken`, `sessionid`, or any future cookie.
    """
    out: list[Tuple[str, str]] = []
    if not header:
        return out
    for chunk in header.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, _, value = chunk.partition("=")
        out.append((name.strip(), value.strip()))
    return out


def get_cookie(headers: Mapping[bytes, bytes] | Iterable[Tuple[bytes, bytes]],
               name: str) -> Optional[str]:
    """Read a single cookie value from an ASGI/Django headers mapping.

    `headers` may be:
      * a dict[bytes, bytes] (Django request.headers after conversion), or
      * an iterable of (bytes, bytes) tuples (raw ASGI scope['headers']).

    Returns the cookie value as a str, or None if absent.
    """
    # Normalize to a sequence of (bytes, bytes) pairs.
    pairs: Iterable[Tuple[bytes, bytes]]
    if isinstance(headers, dict):
        pairs = headers.items()
    else:
        pairs = headers
    for k, v in pairs:
        if k.lower() == b"cookie":
            try:
                header = v.decode("latin-1")
            except Exception:
                return None
            for cname, cvalue in _split_cookie_header(header):
                if cname == name:
                    return cvalue
            return None
    return None
