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

# Installiere nur die wirklich benötigten Abhängigkeiten
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    redis-tools \
    supervisor \
    gcc \
    libc6-dev \
    netcat-openbsd \
    net-tools \
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

# Kopiere die Quellcodedateien
COPY tasks.py .
COPY api/ ./api/
COPY core/ ./core/
COPY config/ ./config/
COPY openaicache/ ./openaicache/
COPY services/ ./services/
COPY .env.example ./.env.example

# Supervisord-Konfiguration
COPY config/supervisor-worker.conf /etc/supervisor/conf.d/supervisord.conf

# Datei-Deskriptoren-Limit erhöhen
RUN echo "* soft nofile 65536" >> /etc/security/limits.conf && \
    echo "* hard nofile 65536" >> /etc/security/limits.conf

# Ändere den Besitzer aller Dateien
RUN chown -R appuser:appuser /app /var/log

# Healthcheck für Worker
HEALTHCHECK --interval=60s --timeout=30s --start-period=60s --retries=3 \
    CMD ps aux | grep celery | grep -v grep || exit 1

# Kopiere und aktiviere das Startskript
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Celery Worker Konfiguration für bessere Stabilität
ENV CELERY_WORKERS=1 \
    CELERY_MAX_TASKS_PER_CHILD=10 \
    CELERY_MAX_MEMORY_PER_CHILD=512000 \
    CELERY_DISABLE_RATE_LIMITS=1 \
    CELERY_WORKER_PREFETCH_MULTIPLIER=1 \
    CELERY_WORKER_WITHOUT_HEARTBEAT=1 \
    CELERY_WORKER_WITHOUT_GOSSIP=1 \
    CELERY_WORKER_WITHOUT_MINGLE=1 \
    CELERY_WORKER_SEND_TASK_EVENTS=0 \
    CELERY_POOL=solo \
    LOG_PREFIX="[WORKER] " \
    LOG_LEVEL="INFO" \
    LOG_API_REQUESTS="true" \
    C_FORCE_ROOT=1 \
    CELERY_BROKER_CONNECTION_RETRY=true \
    CELERY_BROKER_CONNECTION_MAX_RETRIES=10 \
    CELERY_BROKER_CONNECTION_TIMEOUT=30 \
    CELERY_BROKER_POOL_LIMIT=1 \
    CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS=false \
    CELERY_TASK_ACKS_LATE=false

# Starte den Container mit dem Startskript
CMD ["/app/start.sh"] 