# Multi-Stage Build für optimierte Container-Größe
FROM python:3.10-slim AS builder

# Build-Abhängigkeiten installieren
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis festlegen
WORKDIR /build

# Abhängigkeiten kopieren und vorbauen
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt && \
    pip wheel --no-cache-dir --wheel-dir=/wheels requests==2.32.3 psutil==5.9.5 backoff==2.2.1

# Finales Image
FROM python:3.10-slim

# Umgebungsvariablen setzen
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Europe/Zurich \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/backend:/app/backend/worker:/app/backend/main \
    CONTAINER_TYPE=worker \
    RUN_MODE=worker \
    USE_SUPERVISOR=false \
    DO_APP_PLATFORM=true \
    USE_COLORED_LOGS=true \
    DIGITAL_OCEAN_DEPLOYMENT=true \
    # Speicherverwaltung für bessere Stabilität
    PYTHONMALLOC=malloc \
    MALLOC_TRIM_THRESHOLD_=65536 \
    REDIS_FALLBACK_URLS="api,api.backend,api.hackthestudy-backend,api:6379,localhost:6379,redis:6379"

# Laufzeitabhängigkeiten installieren
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    redis-tools \
    netcat-openbsd \
    poppler-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Nicht-Root-Benutzer erstellen
RUN useradd -m -u 1000 appuser

# Arbeitsverzeichnis festlegen
WORKDIR /app

# Verzeichnisstruktur erstellen (angepasst für die tatsächlich vorhandenen Verzeichnisse)
RUN mkdir -p /app/config /app/health /app/redis_utils /app/tasks /app/utils \
    /var/log/app /var/log/hackthestudy \
    && touch /var/log/worker-stdout.log /var/log/worker-stderr.log \
    && chmod 666 /var/log/worker-stdout.log /var/log/worker-stderr.log \
    && chmod 777 /var/log/hackthestudy

# Wheels und requirements.txt aus dem Builder-Stage kopieren
COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements.txt /app/requirements.txt

# Abhängigkeiten installieren (vereinfacht)
RUN pip install --no-index --find-links=/wheels -r /app/requirements.txt \
    && rm -rf /wheels

# Basisstruktur erstellen
RUN mkdir -p /app/core && touch /app/core/__init__.py

# Anwendungsdateien kopieren - nur die tatsächlich vorhandenen Dateien und Verzeichnisse
COPY app.py .
COPY config/ ./config/
COPY redis_utils/ ./redis_utils/
COPY tasks/ ./tasks/
COPY health/ ./health/
COPY utils/ ./utils/

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

# Datei-Deskriptoren-Limit erhöhen
RUN echo "* soft nofile 65536" >> /etc/security/limits.conf && \
    echo "* hard nofile 65536" >> /etc/security/limits.conf

# Dateibesitzer ändern
RUN chown -R appuser:appuser /app /var/log

# Verbesserter Healthcheck für Worker
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/ping || exit 1

# Port für Health-Check
EXPOSE 8080

# Als appuser ausführen (statt root) - verbesserte Sicherheit
USER appuser

# Starte den Worker mit dem neuen Entrypoint-Skript
CMD ["/app/entrypoint.sh"] 