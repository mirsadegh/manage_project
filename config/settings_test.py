from .settings import *

# Test database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Remove debug toolbar from installed apps for testing
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'debug_toolbar']

# Remove debug toolbar middleware
MIDDLEWARE = [middleware for middleware in MIDDLEWARE if 'debug_toolbar' not in middleware]

# Disable migrations for faster tests
class DisableMigrations:
    def __contains__(self, item):
        return True
    
    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()

# Use fast password hasher for tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable caching
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Disable celery tasks
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable virus scanning in tests
VIRUS_SCANNING_ENABLED = False

# Email backend for testing
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Disable throttling in tests
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon': '1000/hour',
    'user': '10000/hour',
    'login': '1000/hour',
}

# Debug toolbar disabled
DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda request: False,
}