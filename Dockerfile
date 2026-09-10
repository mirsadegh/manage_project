# Multi-stage Dockerfile for Django backend
# Stage 1: Install dependencies (cached unless requirements change)
FROM python:3.13-slim AS deps

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libmagic1 \
    clamav-daemon \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt /tmp/requirements-prod.txt
RUN pip install --no-cache-dir -r /tmp/requirements-prod.txt

# Stage 2: Runtime image
FROM deps AS runtime

WORKDIR /app

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy application code
COPY . /app/

# Create required directories
RUN mkdir -p /app/logs /app/media /app/staticfiles \
    && chown -R appuser:appuser /app

# Collect static files
RUN DJANGO_ENV=production SECRET_KEY=build-placeholder \
    python manage.py collectstatic --noinput 2>/dev/null || true

USER appuser

EXPOSE 8000

# Default: run daphne (ASGI server for Channels support)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]

# Stage 3: Development image (dev deps on top of prod base)
FROM deps AS dev

WORKDIR /app

COPY requirements-prod.txt /tmp/requirements-prod.txt
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt

# Default: runserver with live reload via bind mount (see docker-compose.dev.yml)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
