# Multi-Stage Build für optimierte Container-Größe
FROM python:3.10-slim AS builder

# Build-Abhängigkeiten nur für den Build-Prozess
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
    pip wheel --no-cache-dir --wheel-dir=/wheels gunicorn==21.2.0 requests==2.31.0 psycopg2-binary==2.9.5 gevent==23.9.1

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
    FLASK_APP=app.py \
    CONTAINER_TYPE=api \
    LOG_API_REQUESTS=true \
    USE_SUPERVISOR=true \
    DO_APP_PLATFORM=true \
    USE_COLORED_LOGS=false \
    GUNICORN_WORKERS=2 \
    DIGITAL_OCEAN_DEPLOYMENT=true \
    PORT=8080

# Installiere nur die für Laufzeit benötigten Abhängigkeiten
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-traditional \
    poppler-utils \
    curl \
    postgresql-client \
    redis-tools \
    redis-server \
    supervisor \
    procps \
    ca-certificates \
    gnupg \
    lsb-release \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Erstelle einen nicht-root Benutzer
RUN useradd -m -u 1000 appuser

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Erstelle alle benötigten Verzeichnisse für die Anwendung und Logs
RUN mkdir -p /app/config /app/core /app/api /app/redis_utils /app/resource_manager \
    /app/tasks /app/health /app/utils /app/bootstrap /app/openaicache \
    /var/run/redis /var/lib/redis /var/log/redis /var/log/app \
    && touch /var/log/supervisord.log /var/log/app-stdout.log /var/log/app-stderr.log \
    && chmod 777 /var/run/redis /var/lib/redis /var/log/redis \
    && chown -R redis:redis /var/run/redis /var/lib/redis /var/log/redis

# Redis-Konfiguration für bessere Stabilität und Performance
RUN sed -i 's/bind 127.0.0.1/bind 0.0.0.0/g' /etc/redis/redis.conf \
    && sed -i 's/protected-mode yes/protected-mode no/g' /etc/redis/redis.conf \
    && sed -i 's/daemonize yes/daemonize no/g' /etc/redis/redis.conf \
    && sed -i 's|pidfile /var/run/redis/redis-server.pid|pidfile /var/run/redis/redis-server.pid|g' /etc/redis/redis.conf \
    && sed -i 's|logfile /var/log/redis/redis-server.log|logfile ""|g' /etc/redis/redis.conf \
    && sed -i 's/databases 16/databases 4/g' /etc/redis/redis.conf \
    && sed -i 's/# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/g' /etc/redis/redis.conf \
    && sed -i 's/# maxmemory <bytes>/maxmemory 128mb/g' /etc/redis/redis.conf

# Kopiere die Wheels und requirements.txt aus dem Builder-Stage
COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements.txt /app/requirements.txt

# Installiere die Abhängigkeiten
RUN pip install --no-index --find-links=/wheels gunicorn requests psycopg2-binary gevent \
    && pip install --no-index --find-links=/wheels -r /app/requirements.txt \
    && rm -rf /wheels

# Erstelle core/__init__.py wenn noch nicht vorhanden
RUN mkdir -p /app/core && touch /app/core/__init__.py

# Kopiere die Anwendungsdateien - optimiert für bessere Organisation
COPY app.py .
COPY health_monitor.py .
COPY api/ ./api/
COPY core/ ./core/
COPY config/ ./config/
COPY redis_utils/ ./redis_utils/
COPY resource_manager/ ./resource_manager/
COPY tasks/ ./tasks/
COPY utils/ ./utils/
COPY bootstrap/ ./bootstrap/
COPY health/ ./health/
COPY openaicache/ ./openaicache/

# Kopiere die Gunicorn-Konfigurationsdatei
COPY config/gunicorn.conf.py ./gunicorn.conf.py

# Supervisord-Konfiguration
COPY config/supervisor-api.conf /etc/supervisor/conf.d/supervisord.conf

# Stelle sicher, dass keine veralteten Socket-Dateien existieren
RUN rm -f /var/run/supervisor.sock /tmp/supervisor-*.sock /tmp/supervisord-*.pid

# Datei-Deskriptoren-Limit erhöhen
RUN echo "* soft nofile 65536" >> /etc/security/limits.conf && \
    echo "* hard nofile 65536" >> /etc/security/limits.conf

# Ändere den Besitzer aller Dateien
RUN chown -R appuser:appuser /app /var/log

# Healthcheck für DigitalOcean App Platform - vereinfacht und zuverlässiger
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/simple-health || exit 1

# Ports freigeben
EXPOSE 8080

# Starte den Container mit dem Supervisor direkt
CMD exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf 