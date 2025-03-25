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
    PIP_NO_CACHE_DIR=1 \
    FLASK_APP=app.py \
    CONTAINER_TYPE=api \
    LOG_API_REQUESTS=true

# Installiere Abhängigkeiten mit geringerem Speicherverbrauch
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    poppler-utils \
    curl \
    postgresql-client \
    redis-tools \
    redis-server \
    supervisor \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Erstelle einen nicht-root Benutzer
RUN useradd -m -u 1000 appuser

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Erstelle alle benötigten Verzeichnisse für die Anwendung und Logs
RUN mkdir -p /app/config /app/core /app/services /app/api /app/openaicache \
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
    && sed -i 's/# maxmemory <bytes>/maxmemory 256mb/g' /etc/redis/redis.conf

# Abhängigkeiten kopieren und installieren (zuerst nur requirements.txt für besseres Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install gunicorn==21.2.0

# Kopiere die lokalen Dateien
COPY app.py .
COPY api/ ./api/
COPY core/ ./core/
COPY config/ ./config/
COPY openaicache/ ./openaicache/
COPY services/ ./services/
COPY .env.example ./.env.example

# Supervisord-Konfiguration
COPY config/supervisor-api.conf /etc/supervisor/conf.d/supervisord.conf

# Stelle zusätzlich sicher, dass die Socket-Datei entfernt wird, falls sie existiert
RUN rm -f /var/run/supervisor.sock && \
    # Debugging: Überprüfe, ob die Supervisor-Konfiguration existiert
    ls -la /etc/supervisor/conf.d/ && \
    cat /etc/supervisor/conf.d/supervisord.conf

# Datei-Deskriptoren-Limit erhöhen
RUN echo "* soft nofile 65536" >> /etc/security/limits.conf && \
    echo "* hard nofile 65536" >> /etc/security/limits.conf

# Ändere den Besitzer aller Dateien
RUN chown -R appuser:appuser /app /var/log

# Healthcheck hinzufügen für bessere Stabilität
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

# Kopiere und aktiviere das Startskript
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Ports freigeben
EXPOSE 8080

# Starte den Container mit dem Startskript
CMD ["/app/start.sh"] 