# Verwende offizielles Python-Image als Basis
FROM python:3.9-slim

# Installiere netcat für Warte-Skripte
RUN apt-get update && apt-get install -y netcat-openbsd

# Erstelle einen nicht-root Benutzer
RUN useradd -m -u 1000 appuser

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Abhängigkeiten kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Projekt-Dateien kopieren
COPY . .

# Ändere den Besitzer des Arbeitsverzeichnisses
RUN chown -R appuser:appuser /app

# Wechsle zum nicht-root Benutzer
USER appuser

# Port 5000 freigeben (Flask läuft auf diesem Port)
EXPOSE 5000

# Umgebungsvariablen für Flask setzen
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Skripte ausführbar machen
RUN chmod +x /app/start.sh
RUN chmod +x /app/start-worker.sh

# Standardmäßig start.sh ausführen (wird vom worker überschrieben)
CMD ["/bin/bash", "/app/start.sh"]