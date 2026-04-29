COMPOSE ?= docker compose

.PHONY: help build up down restart ps logs backend-logs frontend-logs db-logs \
	dev dev-down test test-v shell-backend shell-db migrate createsuperuser

help:
	@echo "Available targets:"
	@echo "  make build          Build all images"
	@echo "  make up             Start default stack (db, backend, frontend, redis)"
	@echo "  make down           Stop and remove containers"
	@echo "  make restart        Restart default stack"
	@echo "  make ps             Show service status"
	@echo "  make logs           Follow all logs"
	@echo "  make backend-logs   Follow backend logs"
	@echo "  make frontend-logs  Follow frontend logs"
	@echo "  make db-logs        Follow database logs"
	@echo "  make dev            Start dev profile (backend-dev)"
	@echo "  make dev-down       Stop dev profile"
	@echo "  make test           Run test profile (test-runner)"
	@echo "  make test-v         Run test profile with verbose pytest"
	@echo "  make migrate        Run Django migrations on backend"
	@echo "  make createsuperuser Create Django superuser on backend"
	@echo "  make shell-backend  Open shell in backend container"
	@echo "  make shell-db       Open psql in db container"

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) down
	$(COMPOSE) up -d --build

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f

backend-logs:
	$(COMPOSE) logs -f backend

frontend-logs:
	$(COMPOSE) logs -f frontend

db-logs:
	$(COMPOSE) logs -f db

dev:
	COMPOSE_PROFILES=dev $(COMPOSE) up -d --build backend-dev

dev-down:
	COMPOSE_PROFILES=dev $(COMPOSE) down

test:
	COMPOSE_PROFILES=test $(COMPOSE) up --build --abort-on-container-exit --exit-code-from test-runner test-runner

test-v:
	COMPOSE_PROFILES=test $(COMPOSE) run --rm test-runner sh -c "pytest /tests -vv"

migrate:
	$(COMPOSE) exec backend python manage.py migrate

createsuperuser:
	$(COMPOSE) exec backend python manage.py createsuperuser

shell-backend:
	$(COMPOSE) exec backend sh

shell-db:
	$(COMPOSE) exec db psql -U $$DB_USER -d $$DB_NAME
