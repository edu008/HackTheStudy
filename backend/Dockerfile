# Verwende offizielles Python-Image als Basis
FROM python:3.9-slim

# Installiere netcat für Warte-Skripte und poppler-utils für PDF-Verarbeitung
RUN apt-get update && apt-get install -y netcat-openbsd poppler-utils

# Erstelle einen nicht-root Benutzer
RUN useradd -m -u 1000 appuser

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Abhängigkeiten kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Projekt-Dateien kopieren
COPY . .

# Stelle sicher, dass das docker_logs-Paket korrekt installiert ist
RUN python -c "import sys; sys.path.insert(0, '/app'); import docker_logs" || echo "Docker-Logs werden beim Start initialisiert"

# Mache die verbesserten Logging-Skripte ausführbar
RUN chmod +x /app/start.sh
RUN chmod +x /app/start-worker.sh
RUN chmod +x /app/app_wrapper.py
RUN chmod +x /app/docker_logs/test_logs.py

# Ändere den Besitzer des Arbeitsverzeichnisses
RUN chown -R appuser:appuser /app

# Wechsle zum nicht-root Benutzer
USER appuser

# Port 5000 freigeben (Flask läuft auf diesem Port)
EXPOSE 5000

# Umgebungsvariablen für Flask setzen
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV USE_COLORED_LOGS=true
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Standardmässig start.sh ausführen (wird vom worker überschrieben)
CMD ["/bin/bash", "/app/start.sh"]