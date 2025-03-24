# Verwende offizielles Python-Image als Basis
FROM python:3.10-slim

# Setze Umgebungsvariablen für Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Europe/Zurich \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    CONTAINER_TYPE=worker \
    RUN_MODE=worker

# Installiere Abhängigkeiten mit geringerem Speicherverbrauch
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    poppler-utils \
    curl \
    postgresql-client \
    redis-tools \
    supervisor \
    gcc \
    libc6-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Erstelle einen nicht-root Benutzer
RUN useradd -m -u 1000 appuser

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Erstelle alle benötigten Verzeichnisse für die Anwendung und Logs
RUN mkdir -p /app/config /app/core /app/services /app/api /app/openaicache \
    /var/log/app \
    && touch /var/log/supervisord.log /var/log/worker-stdout.log /var/log/worker-stderr.log

# Abhängigkeiten kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Kopiere die notwendigen Dateien aus dem Backend-Verzeichnis
COPY ../tasks.py .
COPY ../api ./api
COPY ../core ./core
COPY ../config ./config
COPY ../openaicache ./openaicache
COPY ../services ./services
COPY ../.env.example ./.env.example

# Supervisord-Konfiguration
COPY ../config/supervisor-worker.conf /etc/supervisor/conf.d/supervisord.conf

# Datei-Deskriptoren-Limit erhöhen
RUN echo "* soft nofile 65536" >> /etc/security/limits.conf && \
    echo "* hard nofile 65536" >> /etc/security/limits.conf

# Ändere den Besitzer aller Dateien
RUN chown -R appuser:appuser /app /var/log

# Healthcheck für Worker
HEALTHCHECK --interval=60s --timeout=30s --start-period=60s --retries=3 \
    CMD ps aux | grep celery | grep -v grep || exit 1

# Celery Worker Konfiguration für bessere Stabilität
ENV CELERY_WORKERS=1 \
    CELERY_MAX_TASKS_PER_CHILD=1 \
    CELERY_DISABLE_RATE_LIMITS=1 \
    CELERY_WORKER_PREFETCH_MULTIPLIER=1 \
    CELERY_WORKER_WITHOUT_HEARTBEAT=1 \
    CELERY_WORKER_WITHOUT_GOSSIP=1 \
    CELERY_WORKER_WITHOUT_MINGLE=1 \
    CELERY_WORKER_SEND_TASK_EVENTS=0 \
    CELERY_POOL=solo \
    BILLIARD_DEBUG=1 \
    LOG_PREFIX="[WORKER] " \
    LOG_LEVEL="INFO" \
    LOG_API_REQUESTS="true"

# Starte den Container mit Hilfe von Supervisor
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"] 