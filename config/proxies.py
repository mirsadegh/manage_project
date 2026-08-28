# config/proxies.py

"""
PR-3 Fix #2: trusted-proxy allowlist for X-Forwarded-For.

Only honor the X-Forwarded-For / X-Real-IP headers when the immediate
peer (scope['client']) is in settings.TRUSTED_PROXY_CIDRS. Otherwise
the header is treated as untrusted client input and the peer's address
is used directly. This prevents an attacker from spoofing their IP to
bypass per-IP rate limits.
"""
import ipaddress
import logging

from django.conf import settings


logger = logging.getLogger(__name__)


def _parse_headers(headers):
    """Convert ASGI headers (list of byte pairs) into a dict of lowercased str keys."""
    out = {}
    for name, value in headers or []:
        try:
            key = name.decode('latin-1').lower() if isinstance(name, (bytes, bytearray)) else name.lower()
            val = value.decode('latin-1') if isinstance(value, (bytes, bytearray)) else value
            out[key] = val
        except Exception:
            continue
    return out


def _trusted_cidrs():
    raw = getattr(settings, 'TRUSTED_PROXY_CIDRS', None) or []
    networks = []
    for cidr in raw:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except (ValueError, TypeError):
            logger.warning('TRUSTED_PROXY_CIDRS: ignoring invalid entry %r', cidr)
    return networks


def get_client_ip(scope):
    """Resolve the real client IP for a WebSocket / ASGI scope.

    Returns '0.0.0.0' if no client address is available.
    """
    client = scope.get('client') or ('', 0)
    remote_addr = client[0] if client else ''
    if not remote_addr:
        return '0.0.0.0'

    networks = _trusted_cidrs()
    if not networks:
        # No proxies are trusted: always use the immediate peer.
        return remote_addr

    try:
        remote_ip = ipaddress.ip_address(remote_addr)
    except ValueError:
        return remote_addr

    if not any(remote_ip in net for net in networks):
        return remote_addr

    # Peer is a trusted proxy; honor forwarded headers (left-most is original client).
    headers = _parse_headers(scope.get('headers'))
    xff = headers.get('x-forwarded-for')
    if xff:
        return xff.split(',')[0].strip()
    x_real_ip = headers.get('x-real-ip')
    if x_real_ip:
        return x_real_ip.strip()
    return remote_addr
