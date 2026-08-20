from django.test import TestCase
from django.core.cache import cache
from asgiref.sync import async_to_sync
from rest_framework_simplejwt.tokens import AccessToken

from accounts.tests.factories import UserFactory
from config.websocket_auth import get_user_from_token


class WebSocketTokenCacheKeyTest(TestCase):
    """B21: WS token cache key must be a stable SHA-256 digest, not builtin hash()."""

    def test_cache_key_is_stable_sha256_across_calls(self):
        import hashlib

        captured = []

        orig_get = cache.get
        orig_set = cache.set

        def fake_get(key):
            captured.append(key)
            return orig_get(key)

        def fake_set(key, value, timeout=None):
            captured.append(key)
            return orig_set(key, value, timeout)

        cache.get = fake_get
        cache.set = fake_set
        try:
            user = UserFactory()
            token = str(AccessToken.for_user(user))

            # Two independent validation calls with the same token.
            result1 = async_to_sync(get_user_from_token)(token)
            result2 = async_to_sync(get_user_from_token)(token)
        finally:
            cache.get = orig_get
            cache.set = orig_set

        self.assertTrue(result1.is_valid)
        self.assertTrue(result2.is_valid)
        self.assertEqual(result1.user.id, user.id)
        self.assertEqual(result2.user.id, user.id)

        expected = f"ws_token_{hashlib.sha256(token.encode()).hexdigest()}"

        # Every captured key must equal the deterministic SHA-256 key...
        for key in captured:
            self.assertEqual(key, expected)
            self.assertEqual(len(key), len("ws_token_") + 64)

        # ...and the two calls must produce the same key (stable, process-independent).
        self.assertEqual(captured[0], captured[-1])
