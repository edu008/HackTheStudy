# Verwende offizielles Python-Image als Basis
FROM python:3.10-slim

# Setze Umgebungsvariablen für Python (kein Puffern, UTF-8-Kodierung)
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Europe/Zurich

# Installiere Abhängigkeiten
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
       /var/log/worker-stdout.log /var/log/worker-stderr.log /var/log/payment-stdout.log \
       /var/log/payment-stderr.log \
    && chmod 777 /var/run/redis /var/lib/redis /var/log/redis \
    && chown -R redis:redis /var/run/redis /var/lib/redis /var/log/redis

# Redis-Konfiguration korrigieren
RUN sed -i 's/bind 127.0.0.1/bind 0.0.0.0/g' /etc/redis/redis.conf
RUN sed -i 's/protected-mode yes/protected-mode no/g' /etc/redis/redis.conf
RUN sed -i 's/daemonize yes/daemonize no/g' /etc/redis/redis.conf
RUN sed -i 's|pidfile /var/run/redis/redis-server.pid|pidfile /var/run/redis/redis-server.pid|g' /etc/redis/redis.conf
RUN sed -i 's|logfile /var/log/redis/redis-server.log|logfile ""|g' /etc/redis/redis.conf

# Abhängigkeiten kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere den Quellcode
COPY . .

# Konfigurationsdateien kopieren
COPY config/supervisor.conf /etc/supervisor/conf.d/supervisord.conf
COPY config/redis.conf /app/config/
COPY config/env_handler.py /app/config/

# Anwendungsdateien kopieren
COPY core/*.py /app/core/
COPY api/ /app/api/
COPY openaicache/ /app/openaicache/
COPY services/*.py /app/services/
COPY docker_logs/ /app/docker_logs/
COPY app.py tasks.py /app/
COPY .env.example /app/

# Ändere den Besitzer aller Dateien
RUN chown -R appuser:appuser /app /var/log

# Wechsle zum nicht-root Benutzer für mehr Sicherheit
USER appuser

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
    BILLIARD_DEBUG=1

# Starte den Container mit Hilfe von Supervisor
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]