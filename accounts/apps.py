from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        # PR-3 Fix #1: bridge BlacklistedToken -> WS force_disconnect.
        from . import signals  # noqa: F401
