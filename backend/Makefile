.PHONY: clean test lint run migrate reset-db

# Standardziel
all: lint test

# Entwicklungsserver starten
run:
	python app.py

# Datenbank-Migration durchführen
migrate:
	flask db upgrade

# Tests ausführen
test:
	pytest

# Testabdeckung anzeigen
coverage:
	pytest --cov=. --cov-report=term --cov-report=html:coverage_report
	@echo "Öffne coverage_report/index.html im Browser, um detaillierte Testabdeckung zu sehen"

# Lint mit flake8
lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

# Umfassendere Codeprüfung mit pylint
lint-full:
	pylint --rcfile=.pylintrc **/*.py

# Datenbank zurücksetzen
reset-db:
	flask db_reset

# Entwicklungsumgebung aufsetzen
setup-dev:
	pip install -r requirements-dev.txt
	pre-commit install

# Docker-Container bauen
docker-build:
	docker-compose build

# Docker-Container starten
docker-up:
	docker-compose up -d

# Docker-Container stoppen
docker-down:
	docker-compose down

# Bereinigen von temporären Dateien und Caches
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".coverage" -delete
	find . -type d -name "coverage_report" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name "dist" -exec rm -rf {} +
	find . -type d -name "build" -exec rm -rf {} +

# Hilfe anzeigen
help:
	@echo "Verfügbare Befehle:"
	@echo "  make run              - Entwicklungsserver starten"
	@echo "  make test             - Tests ausführen"
	@echo "  make coverage         - Testabdeckung anzeigen"
	@echo "  make lint             - Grundlegende Codeprüfung ausführen"
	@echo "  make lint-full        - Umfassende Codeprüfung ausführen"
	@echo "  make migrate          - Datenbank-Migration durchführen"
	@echo "  make reset-db         - Datenbank zurücksetzen"
	@echo "  make docker-build     - Docker-Container bauen"
	@echo "  make docker-up        - Docker-Container starten"
	@echo "  make docker-down      - Docker-Container stoppen"
	@echo "  make clean            - Temporäre Dateien und Caches bereinigen"
	@echo "  make setup-dev        - Entwicklungsumgebung aufsetzen" 