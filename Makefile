.DEFAULT_GOAL := help
.PHONY: help dev down test backend.test frontend.test lint backend.lint frontend.lint migrate openapi codegen gen-jwt-keys seed-platform-staff

help:
	@echo "FastSaaS platform — common dev tasks"
	@echo ""
	@echo "  make dev               docker-compose up + backend + frontend (foreground)"
	@echo "  make down              stop docker-compose services + clean volumes"
	@echo "  make migrate           run alembic upgrade head (as alembic_migrator)"
	@echo "  make test              backend pytest + frontend vitest"
	@echo "  make backend.test      backend pytest only"
	@echo "  make frontend.test     frontend vitest only"
	@echo "  make lint              backend ruff + frontend lint"
	@echo "  make openapi           dump openapi.json from backend"
	@echo "  make codegen           regenerate frontend/src/api/generated/ from openapi.json"
	@echo "  make seed-platform-staff USER_EMAIL=...  flip is_platform_staff=TRUE on a user actor"

dev:
	docker compose up -d
	@echo "Postgres / Redis / Mailhog up. Start backend (make -C backend dev) and frontend (make -C frontend dev) in separate shells."

down:
	docker compose down -v

migrate:
	cd backend && uv run alembic upgrade head

backend.test:
	cd backend && uv run pytest

frontend.test:
	cd frontend && npm test -- --run

test: backend.test frontend.test

backend.lint:
	cd backend && uv run ruff check .

frontend.lint:
	cd frontend && npm run lint

lint: backend.lint frontend.lint

openapi:
	cd backend && uv run python -c "import json; from fastsaas.main import app; print(json.dumps(app.openapi(), indent=2))" > openapi.json
	@echo "Wrote backend/openapi.json"

codegen: openapi
	cd frontend && npm run codegen

seed-platform-staff:
	@if [ -z "$(USER_EMAIL)" ]; then \
		echo "usage: make seed-platform-staff USER_EMAIL=alice@example.com"; \
		exit 2; \
	fi
	cd backend && uv run python -m fastsaas.scripts.seed_platform_staff "$(USER_EMAIL)"

gen-jwt-keys:
	@kid=$${KID:-dev-1}; \
	dir=infra/dev-secrets/jwt; \
	mkdir -p $$dir; \
	openssl genpkey -algorithm RSA -out $$dir/$$kid.pem -pkeyopt rsa_keygen_bits:2048 2>/dev/null; \
	openssl rsa -in $$dir/$$kid.pem -pubout -out $$dir/$$kid.pub.pem 2>/dev/null; \
	chmod 600 $$dir/$$kid.pem; \
	echo "Wrote $$dir/$$kid.pem and $$dir/$$kid.pub.pem"
