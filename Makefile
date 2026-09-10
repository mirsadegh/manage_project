.PHONY: dev-up dev-down dev-logs dev-shell dev-migrate up down migrate shell logs test lint help

# Development mode (bind mounts, hot reload)
dev-up:
	docker compose -f docker-compose.dev.yml up --build

dev-down:
	docker compose -f docker-compose.dev.yml down

dev-logs:
	docker compose -f docker-compose.dev.yml logs -f

dev-shell:
	docker compose -f docker-compose.dev.yml exec web python manage.py shell

dev-migrate:
	docker compose -f docker-compose.dev.yml exec web python manage.py migrate

dev-test:
	docker compose -f docker-compose.dev.yml exec web python -m pytest --no-cov -v

# Production mode (optimized images)
up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

shell:
	docker compose exec web python manage.py shell

migrate:
	docker compose exec web python manage.py migrate

test:
	docker compose exec web python -m pytest --no-cov -v

# Utilities
createsuperuser:
	docker compose exec web python manage.py createsuperuser

collectstatic:
	docker compose exec web python manage.py collectstatic --noinput

db-backup:
	docker compose exec db pg_dump -U $(POSTGRES_USER) $(POSTGRES_DB) > backup_$$(date +%Y%m%d_%H%M%S).sql

help:
	@echo "Development:"
	@echo "  make dev-up       - Start dev environment with hot reload"
	@echo "  make dev-down     - Stop dev environment"
	@echo "  make dev-logs     - Follow dev logs"
	@echo "  make dev-shell    - Django shell in dev container"
	@echo "  make dev-migrate  - Run migrations in dev"
	@echo "  make dev-test     - Run tests in dev"
	@echo ""
	@echo "Production:"
	@echo "  make up           - Build and start production"
	@echo "  make down         - Stop production"
	@echo "  make logs         - Follow production logs"
	@echo "  make shell        - Django shell in prod container"
	@echo "  make migrate      - Run migrations in prod"
	@echo "  make test         - Run tests in prod"
	@echo ""
	@echo "Utilities:"
	@echo "  make createsuperuser  - Create admin user"
	@echo "  make collectstatic    - Collect static files"
	@echo "  make db-backup        - Backup database"

</content>