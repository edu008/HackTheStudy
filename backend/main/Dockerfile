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
    USE_SUPERVISOR=false \
    DO_APP_PLATFORM=true \
    USE_COLORED_LOGS=false \
    DIGITAL_OCEAN_DEPLOYMENT=true \
    PORT=8080 \
    HEALTH_PORT=8081 \
    # Redis- und OpenAI-Cache-Konfiguration
    REDIS_URL=redis://localhost:6379/0 \
    REDIS_HOST=localhost \
    REDIS_PASSWORD=hackthestudy_redis_password \
    OPENAI_CACHE_ENABLED=true \
    OPENAI_CACHE_TTL=86400 \
    OPENAI_MAX_RETRIES=3

# Installiere nur die für Laufzeit benötigten Abhängigkeiten
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-traditional \
    poppler-utils \
    curl \
    postgresql-client \
    redis-tools \
    redis-server \
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
    /var/run/redis /var/lib/redis /var/log/redis /var/log/app /var/log/hackthestudy \
    && touch /var/log/app-stdout.log /var/log/app-stderr.log \
    && chmod 777 /var/run/redis /var/lib/redis /var/log/redis /var/log/hackthestudy \
    && chown -R redis:redis /var/run/redis /var/lib/redis /var/log/redis

# Redis-Konfiguration für bessere Stabilität und Performance
RUN sed -i 's/bind 127.0.0.1/bind 0.0.0.0/g' /etc/redis/redis.conf \
    && sed -i 's/protected-mode yes/protected-mode no/g' /etc/redis/redis.conf \
    && sed -i 's/daemonize yes/daemonize no/g' /etc/redis/redis.conf \
    && sed -i 's|pidfile /var/run/redis/redis-server.pid|pidfile /var/run/redis/redis-server.pid|g' /etc/redis/redis.conf \
    && sed -i 's|logfile /var/log/redis/redis-server.log|logfile ""|g' /etc/redis/redis.conf \
    && sed -i 's/databases 16/databases 4/g' /etc/redis/redis.conf \
    && sed -i 's/# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/g' /etc/redis/redis.conf \
    && sed -i 's/# maxmemory <bytes>/maxmemory 256mb/g' /etc/redis/redis.conf \
    && sed -i 's/save 900 1/save 3600 1/g' /etc/redis/redis.conf \
    && sed -i 's/save 300 10/save ""/' /etc/redis/redis.conf \
    && sed -i 's/save 60 10000/save ""/' /etc/redis/redis.conf \
    && sed -i 's/# requirepass foobared/requirepass ${REDIS_PASSWORD}/g' /etc/redis/redis.conf

# Kopiere die Wheels und requirements.txt aus dem Builder-Stage
COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements.txt /app/requirements.txt

# Installiere die Abhängigkeiten
RUN pip install --no-index --find-links=/wheels gunicorn requests psycopg2-binary gevent \
    && pip install --no-index --find-links=/wheels -r /app/requirements.txt \
    && rm -rf /wheels

# Prüfe, ob Gunicorn korrekt installiert wurde
RUN gunicorn --version || pip install gunicorn==21.2.0

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

# Datei-Deskriptoren-Limit erhöhen
RUN echo "* soft nofile 65536" >> /etc/security/limits.conf && \
    echo "* hard nofile 65536" >> /etc/security/limits.conf

# Ändere den Besitzer aller Dateien
RUN chown -R appuser:appuser /app /var/log

# Ports freigeben
EXPOSE 8080 8081 6379

# Healthcheck für DigitalOcean App Platform - optimiert für einen primären Endpunkt
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Wechsle zum nicht-root Benutzer für mehr Sicherheit
USER appuser

# Starte Redis im Hintergrund und dann die Flask-Anwendung
CMD /usr/bin/redis-server /etc/redis/redis.conf --daemonize yes && \
    echo "Redis gestartet, warte 2 Sekunden..." && \
    sleep 2 && \
    redis-cli -a ${REDIS_PASSWORD} ping && \
    echo "Redis bereit, starte Flask-App..." && \
    export FLASK_APP=app.py && \
    export FLASK_RUN_HOST=0.0.0.0 && \
    export FLASK_RUN_PORT=${PORT} && \
    export APP_PORT=${PORT} && \
    export HEALTH_PORT=${HEALTH_PORT} && \
    python app.py 