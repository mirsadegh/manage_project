"""Health check endpoint for Docker/Kubernetes probes."""
from django.http import JsonResponse
from django.db import connection
from django.conf import settings


def healthz(request):
    """
    Lightweight health check. Returns 200 if DB and Redis are reachable.
    Safe to call frequently - no auth required, minimal queries.
    """
    status = {"status": "ok", "checks": {}}
    http_status = 200

    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        status["checks"]["database"] = "ok"
    except Exception as e:
        status["checks"]["database"] = f"error: {str(e)[:100]}"
        http_status = 503

    # Redis check
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_timeout=2)
        r.ping()
        status["checks"]["redis"] = "ok"
    except Exception as e:
        status["checks"]["redis"] = f"error: {str(e)[:100]}"
        http_status = 503

    # ClamAV check (optional - don't fail health if unavailable)
    try:
        import pyclamd
        cd = pyclamd.ClamdUnixSocket()
        cd.ping()
        status["checks"]["clamav"] = "ok"
    except Exception:
        status["checks"]["clamav"] = "unavailable"

    if http_status != 200:
        status["status"] = "degraded"

    return JsonResponse(status, status=http_status)
