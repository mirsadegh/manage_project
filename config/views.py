from django.http import JsonResponse


def root(request):
    return JsonResponse({
        "status": "ok",
        "message": "Django backend is running",
        "endpoints": {
            "admin": "/admin/",
            "api": "/api/",
            "swagger": "/api/docs/",
            "redoc": "/api/redoc/",
            "schema": "/api/schema/",
        },
    })
