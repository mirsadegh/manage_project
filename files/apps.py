from django.apps import AppConfig


class FilesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'files'

    def ready(self):
        # M1: cascade-delete Attachments when parent is deleted.
        from .signals import connect_cascade_signals
        connect_cascade_signals()

