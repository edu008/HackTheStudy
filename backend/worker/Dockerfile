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
    pip wheel --no-cache-dir --wheel-dir=/wheels requests==2.31.0 psutil==5.9.5 backoff==2.2.1

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
    PYTHONPATH=/app \
    CONTAINER_TYPE=worker \
    RUN_MODE=worker \
    USE_SUPERVISOR=false \
    DO_APP_PLATFORM=true \
    USE_COLORED_LOGS=false \
    DIGITAL_OCEAN_DEPLOYMENT=true \
    # Celery-Konfiguration für optimierte Leistung
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
    # Logging-Konfiguration
    LOG_PREFIX="[WORKER] " \
    LOG_LEVEL="INFO" \
    LOG_API_REQUESTS="true" \
    # Celery-Broker und Redis-Konfiguration
    C_FORCE_ROOT=1 \
    CELERY_BROKER_CONNECTION_RETRY=true \
    CELERY_BROKER_CONNECTION_MAX_RETRIES=10 \
    CELERY_BROKER_CONNECTION_TIMEOUT=30 \
    CELERY_BROKER_POOL_LIMIT=1 \
    CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS=false \
    CELERY_TASK_ACKS_LATE=true \
    HEALTH_PORT=8080 \
    # OpenAI-Cache-Konfiguration
    OPENAI_CACHE_ENABLED=true \
    OPENAI_CACHE_TTL=86400 \
    OPENAI_MAX_RETRIES=3 \
    # Redis-Authentifizierung
    REDIS_PASSWORD=hackthestudy_redis_password

# Installiere nur die für Laufzeit benötigten Abhängigkeiten
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    redis-tools \
    netcat-openbsd \
    net-tools \
    procps \
    dnsutils \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-deu \
    tesseract-ocr-eng \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Erstelle alle benötigten Verzeichnisse
RUN mkdir -p /app/config /app/core /app/health /app/redis_utils /app/resource_manager /app/tasks /app/utils /app/api /app/openaicache /var/log/app /var/log/hackthestudy

# Kopiere die Wheels und requirements.txt aus dem Builder-Stage
COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements.txt /app/requirements.txt

# Installiere die Abhängigkeiten
RUN pip install --no-index --find-links=/wheels requests==2.31.0 psutil==5.9.5 backoff==2.2.1 \
    && pip install --no-index --find-links=/wheels -r /app/requirements.txt \
    && rm -rf /wheels

# Kopiere die Quellcodedateien der Microservice-Struktur
# Erst die Config-Verzeichnisse kopieren
COPY config/ ./config/

# Danach die restlichen Module
COPY core/ ./core/
COPY health/ ./health/
COPY redis_utils/ ./redis_utils/
COPY resource_manager/ ./resource_manager/
COPY tasks/ ./tasks/
COPY utils/ ./utils/
COPY api/ ./api/
COPY openaicache/ ./openaicache/

# Kopiere die Hauptdateien
COPY app.py .
COPY __init__.py .

# Erstelle Startup-Skript, das auf Redis wartet
RUN echo '#!/bin/bash\n\
echo "Warte auf Redis-Server..."\n\
REDIS_HOST=${REDIS_HOST:-api}\n\
REDIS_PORT=${REDIS_PORT:-6379}\n\
REDIS_WAIT_TIMEOUT=${REDIS_WAIT_TIMEOUT:-90}\n\
\n\
start_time=$(date +%s)\n\
while true; do\n\
    current_time=$(date +%s)\n\
    elapsed_time=$((current_time - start_time))\n\
    \n\
    if [ $elapsed_time -gt $REDIS_WAIT_TIMEOUT ]; then\n\
        echo "Timeout beim Warten auf Redis ($elapsed_time Sekunden). Starte trotzdem..."\n\
        break\n\
    fi\n\
    \n\
    if redis-cli -h $REDIS_HOST -p $REDIS_PORT -a $REDIS_PASSWORD ping > /dev/null 2>&1; then\n\
        echo "Redis ist bereit nach $elapsed_time Sekunden. Starte Worker..."\n\
        break\n\
    else\n\
        echo "Warte auf Redis ($elapsed_time/$REDIS_WAIT_TIMEOUT Sekunden)..."\n\
        sleep 2\n\
    fi\n\
done\n\
\n\
# Starte den Worker\n\
exec python -m app\n' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Erstelle leere Log-Dateien mit korrekten Berechtigungen
RUN mkdir -p /var/log/app /var/log/hackthestudy \
    && touch /var/log/worker-stdout.log /var/log/worker-stderr.log \
    && chmod 666 /var/log/worker-stdout.log /var/log/worker-stderr.log \
    && chmod 777 /var/log/hackthestudy

# Datei-Deskriptoren-Limit erhöhen
RUN echo "* soft nofile 65536" >> /etc/security/limits.conf && \
    echo "* hard nofile 65536" >> /etc/security/limits.conf

# Verbesserter Healthcheck für Worker
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

# Port für Health-Check
EXPOSE 8080

# Umgebungsvariable für verbesserte Redis-Erkennung
ENV REDIS_FALLBACK_URLS="api,api.backend,api.hackthestudy-backend,api:6379,localhost:6379,redis:6379"

# Starte den Worker mit dem neuen Entrypoint-Skript
CMD ["/app/entrypoint.sh"] 