# Multi-Stage Build für optimierte Container-Größe
FROM python:3.10-slim AS builder

# Build-Abhängigkeiten
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis im Container
WORKDIR /build

# Abhängigkeiten kopieren und installieren (nur im Builder-Stage)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt && \
    pip wheel --no-cache-dir --wheel-dir=/wheels requests==2.31.0 psutil==5.9.5

# Finales Image ohne Build-Tools
FROM python:3.10-slim

# DigitalOcean-optimierte Umgebungsvariablen
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Europe/Zurich \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    CONTAINER_TYPE=worker \
    RUN_MODE=worker \
    USE_SUPERVISOR=true \
    DO_APP_PLATFORM=true \
    USE_COLORED_LOGS=false \
    DIGITAL_OCEAN_DEPLOYMENT=true \
    CELERY_WORKERS=1 \
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
    CELERY_TASK_ACKS_LATE=false \
    HEALTH_PORT=8080

# Installiere nur die für Laufzeit benötigten Abhängigkeiten
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    redis-tools \
    supervisor \
    netcat-openbsd \
    net-tools \
    procps \
    dnsutils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Erstelle alle benötigten Verzeichnisse
RUN mkdir -p /app/config /app/core /app/health /app/redis /app/ressource_manager /app/tasks /app/utils /app/api /app/openaicache \
    /var/log/app \
    && touch /var/log/supervisord.log /var/log/worker-stdout.log /var/log/worker-stderr.log

# Kopiere die Wheels und requirements.txt aus dem Builder-Stage
COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements.txt /app/requirements.txt

# Installiere die Abhängigkeiten
RUN pip install --no-index --find-links=/wheels requests==2.31.0 psutil==5.9.5 \
    && pip install --no-index --find-links=/wheels -r /app/requirements.txt \
    && rm -rf /wheels

# Kopiere die Quellcodedateien der neuen Microservice-Struktur
COPY app.py .
COPY __init__.py .
COPY core/ ./core/
COPY health/ ./health/
COPY redis/ ./redis/
COPY ressource_manager/ ./ressource_manager/
COPY tasks/ ./tasks/
COPY utils/ ./utils/
COPY config/ ./config/
COPY api/ ./api/
COPY openaicache/ ./openaicache/
COPY README.md .

# Supervisord-Konfiguration
COPY config/supervisor-worker.conf /etc/supervisor/conf.d/supervisord.conf

# Stelle sicher, dass keine veralteten Socket-Dateien existieren
RUN rm -f /var/run/supervisor.sock /tmp/supervisor-*.sock /tmp/supervisord-*.pid

# Datei-Deskriptoren-Limit erhöhen
RUN echo "* soft nofile 65536" >> /etc/security/limits.conf && \
    echo "* hard nofile 65536" >> /etc/security/limits.conf

# Erstelle einen nicht-root Benutzer
RUN useradd -m -u 1000 appuser

# Ändere den Besitzer aller Dateien
RUN chown -R appuser:appuser /app /var/log

# Verbesserter Healthcheck für Worker
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

# Port für Health-Check
EXPOSE 8080

# Starte den Container mit Supervisor
CMD exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf 