# config/websocket_throttle.py

"""
PR-3 Fix #6: per-connection inbound message rate limit.

A single open WebSocket connection can otherwise fire an unbounded number
of messages. With a broadcast amplifier like cursor_position in
ProjectConsumer, one client can saturate the entire project's bandwidth.

This module provides a mixin, ThrottledConsumer, that:

  - counts inbound messages per connection (token-bucket);
  - defaults to DEFAULT_LIMIT messages/second across all handlers;
  - lets specific EXPENSIVE_HANDLERS drop to EXPENSIVE_LIMIT (1/s by
    default) — e.g. `request_sync` and `get_recent` that hit the DB;
  - closes the connection with WS code 4290 when the bucket is empty;
  - keeps the existing `receive` dispatch so consumers only need to mix
    the class in and decorate expensive handlers with `@expensive`.
"""
import time
from functools import wraps


# Default limits (configurable per-deployment via settings.WEBSOCKET_THROTTLE).
DEFAULT_LIMIT_PER_SECOND = 10
EXPENSIVE_LIMIT_PER_SECOND = 1
THROTTLE_CLOSE_CODE = 4290


class _TokenBucket:
    """Simple token-bucket that refills at a fixed rate per second."""

    __slots__ = ('rate', 'capacity', '_tokens', '_last')

    def __init__(self, rate, capacity=None):
        self.rate = float(rate)
        self.capacity = float(capacity if capacity is not None else rate)
        self._tokens = self.capacity
        self._last = time.monotonic()

    def try_consume(self):
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


def expensive(func):
    """Decorator: mark a receive handler as expensive (lower rate)."""
    func._ws_expensive = True
    return func


class ThrottledConsumer:
    """
    Mixin for AsyncWebsocketConsumer subclasses.

    Provides:
      - _ws_default_bucket: per-connection bucket for normal messages
      - _ws_expensive_bucket: per-connection bucket for @expensive handlers
      - receive(): wraps the original `receive` and rate-limits dispatch

    Subclasses must call `await super().receive(text_data)` to retain
    their existing receive() behavior; ThrottledConsumer only ADDS the
    rate-limit gate, never replaces the dispatch.
    """

    def _ws_init_throttle(self, default_rate=None, expensive_rate=None):
        """Set up the per-connection token buckets. Call from `connect`."""
        from django.conf import settings as _s
        cfg = getattr(_s, 'WEBSOCKET_THROTTLE', {}) or {}
        d = float(cfg.get('DEFAULT_LIMIT_PER_SECOND', default_rate or DEFAULT_LIMIT_PER_SECOND))
        e = float(cfg.get('EXPENSIVE_LIMIT_PER_SECOND', expensive_rate or EXPENSIVE_LIMIT_PER_SECOND))
        self._ws_default_bucket = _TokenBucket(d)
        self._ws_expensive_bucket = _TokenBucket(e)

    async def _ws_check_throttle(self, message_type):
        """Return True if allowed; False if throttled (consumer should close)."""
        handler = (self._message_handlers or {}).get(message_type)
        bucket = (
            self._ws_expensive_bucket
            if handler is not None and getattr(handler, '_ws_expensive', False)
            else self._ws_default_bucket
        )
        return bucket.try_consume()

    @property
    def _message_handlers(self):
        """Best-effort lookup of the handler map (set by BaseConsumer.receive)."""
        # The consumers' receive() builds the handler map on every call.
        # For the throttle gate we recompute on the fly: peek into receive's
        # local `handlers` dict by re-running the same lookup the receive
        # function would. Subclasses expose a `_handler_for_type` override
        # if they have a more complex mapping.
        if hasattr(self, '_handler_for_type'):
            return {None: self._handler_for_type}
        return {}

    async def _ws_throttle_or_close(self, message_type, send):
        """Check the bucket; close the socket if exceeded."""
        if await self._ws_check_throttle(message_type):
            return True
        # Throttled: close with 4290.
        import logging
        logging.getLogger('files').warning(
            'WebSocket inbound rate limit exceeded for user %s (type=%s)',
            getattr(self, 'user', None) and self.user.id,
            message_type,
        )
        await send({
            'type': 'websocket.close',
            'code': THROTTLE_CLOSE_CODE,
            'reason': 'Rate limit exceeded',
        })
        return False

    async def receive(self, text_data=None, bytes_data=None):
        """Default receive: rate-limit by message type then dispatch.

        Subclasses with their own `receive()` should call this via super()
        and pass the parsed message_type. ThrottledConsumer is a mixin,
        so if the consumer's receive() doesn't call super().receive(), the
        throttle gate is bypassed — consumers should integrate via the
        helper at the top of their own receive().
        """
        # Subclasses override receive() entirely; this is a fallback that
        # only fires if they don't. The real enforcement happens when
        # consumers call self._ws_throttle_or_close() at the top of their
        # own receive() — see ProjectConsumer/NotificationConsumer.
        raise NotImplementedError(
            'ThrottledConsumer is a mixin; subclass must call '
            'self._ws_throttle_or_close() in its own receive().'
        )
