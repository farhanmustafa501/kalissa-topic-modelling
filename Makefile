.PHONY: install install-dev test test-cov test-tasks lint lint-flake8 format format-check type-check check clean help docker-up docker-start docker-down docker-restart docker-logs docker-ps

DOCKER_COMPOSE ?= docker compose

help:
	@echo "Available commands:"
	@echo ""
	@echo "Installation:"
	@echo "  make install       - Install production dependencies"
	@echo "  make install-dev   - Install all dependencies (including dev)"
	@echo ""
	@echo "Docker (Recommended):"
	@echo "  make docker-start  - Start the project with Docker Compose (detached)"
	@echo "  make docker-up     - Build and start Docker Compose stack (foreground)"
	@echo "  make docker-down   - Stop the Docker Compose stack"
	@echo "  make docker-restart - Restart the Docker Compose stack"
	@echo "  make docker-logs   - Tail Docker Compose logs"
	@echo "  make docker-ps     - Show running Docker containers"
	@echo ""
	@echo "Testing:"
	@echo "  make test          - Run all tests"
	@echo "  make test-cov      - Run tests with coverage report"
	@echo "  make test-tasks    - Run Celery task tests only"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint          - Run linting checks (ruff)"
	@echo "  make lint-flake8   - Run linting checks (flake8)"
	@echo "  make lint-fix      - Auto-fix linting issues"
	@echo "  make format        - Format code with black and ruff"
	@echo "  make format-check  - Check code formatting without making changes"
	@echo "  make type-check    - Run type checking (mypy)"
	@echo "  make check         - Run all checks (lint, format-check, type-check, test)"
	@echo ""
	@echo "Other:"
	@echo "  make clean         - Clean up generated files"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt -r requirements-dev.txt

test:
	pytest

test-cov:
	pytest --cov=app --cov-report=html --cov-report=term-missing

test-tasks:
	pytest -m task tests/test_tasks.py

lint:
	ruff check app tests

lint-show:
	ruff check app tests --output-format=full

lint-flake8:
	flake8 app tests

lint-fix:
	ruff check --fix app tests

lint-fix-unsafe:
	ruff check --unsafe-fixes --fix app tests

format:
	black app tests
	ruff format app tests

format-check:
	black --check app tests
	ruff format --check app tests

type-check:
	mypy app

docker-up:
	@echo "Starting Docker Compose stack (foreground mode)..."
	@echo "Press Ctrl+C to stop"
	$(DOCKER_COMPOSE) up --build

docker-start:
	@echo "Starting Docker Compose stack in detached mode..."
	$(DOCKER_COMPOSE) up --build -d
	@echo ""
	@echo "Services started! Access the application at http://localhost:8000"
	@echo "View logs with: make docker-logs"
	@echo "Stop services with: make docker-down"

docker-down:
	@echo "Stopping Docker Compose stack..."
	$(DOCKER_COMPOSE) down

docker-restart:
	@echo "Restarting Docker Compose stack..."
	$(DOCKER_COMPOSE) restart

docker-logs:
	$(DOCKER_COMPOSE) logs -f

docker-ps:
	$(DOCKER_COMPOSE) ps

check: lint format-check type-check test
	@echo "All checks passed!"

clean:
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf .coverage
	rm -rf *.pyc
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
