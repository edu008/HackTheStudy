# Verwende offizielles Python-Image als Basis
FROM python:3.10-slim

# Setze Umgebungsvariablen für Python (kein Puffern, UTF-8-Kodierung)
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Europe/Zurich \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1

# Installiere Abhängigkeiten mit geringerem Speicherverbrauch
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    poppler-utils \
    iputils-ping \
    dnsutils \
    curl \
    telnet \
    procps \
    postgresql-client \
    redis-tools \
    redis-server \
    supervisor \
    cron \
    gcc \
    libc6-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Erstelle einen nicht-root Benutzer
RUN useradd -m -u 1000 appuser

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Erstelle alle benötigten Verzeichnisse für die Anwendung und Logs
RUN mkdir -p /app/config /app/core /app/services /app/api /app/openaicache /app/tests \
    /var/run/redis /var/lib/redis /var/log/redis /var/log/app \
    && touch /var/log/supervisord.log /var/log/app-stdout.log /var/log/app-stderr.log \
       /var/log/worker-stdout.log /var/log/worker-stderr.log /var/log/payment-stdout.log \
       /var/log/payment-stderr.log \
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
    && sed -i 's/# maxmemory <bytes>/maxmemory 256mb/g' /etc/redis/redis.conf

# Abhängigkeiten kopieren und installieren (zuerst nur requirements.txt für besseres Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Kopiere Development-Requirements für Tests (optional)
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Kopiere den Quellcode
COPY . .

# Konfigurationsdateien werden nicht extra kopiert, da sie bereits im COPY . . enthalten sind

# Datei-Deskriptoren-Limit erhöhen, um Probleme mit 'invalid file descriptor' zu beheben
RUN echo "* soft nofile 65536" >> /etc/security/limits.conf && \
    echo "* hard nofile 65536" >> /etc/security/limits.conf && \
    echo "root soft nofile 65536" >> /etc/security/limits.conf && \
    echo "root hard nofile 65536" >> /etc/security/limits.conf

# Cron-Job für regelmäßige Bereinigung einrichten
RUN mkdir -p /etc/cron.d && \
    echo "0 */3 * * * root python /app/core/cleanup.py >> /var/log/cron-cleanup.log 2>&1" > /etc/cron.d/cleanup-cron && \
    chmod 0644 /etc/cron.d/cleanup-cron && \
    touch /var/log/cron-cleanup.log && \
    chmod 0666 /var/log/cron-cleanup.log

# Ändere den Besitzer aller Dateien
RUN chown -R appuser:appuser /app /var/log

# Healthcheck hinzufügen für bessere Stabilität
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

# Ports freigeben
EXPOSE 5000 8080

# Umgebungsvariable für CORS setzen
ENV CORS_ORIGINS="https://www.hackthestudy.ch,https://hackthestudy.ch,http://localhost:3000"

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
    # DigitalOcean spezifische Konfiguration
    DO_APP_PLATFORM=true \
    USE_SUPERVISOR=true

# Starte den Container mit Hilfe von Supervisor
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]