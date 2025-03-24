# HackTheStudy Backend: Zwei-Container-Architektur

Dieses Backend verwendet eine Zwei-Container-Architektur für das Deployment auf Digital Ocean App Platform:

## Struktur

- `main/`: API-Container mit Flask und Redis
- `worker/`: Celery-Worker-Container für asynchrone Aufgaben

## Container-Übersicht

### API-Container (main)

Der API-Container stellt die HTTP-API bereit und hostet auch Redis, das als Message Broker für Celery dient.

**Hauptkomponenten:**
- Flask API (app.py)
- Redis Server
- Gunicorn als WSGI-Server

### Worker-Container (worker)

Der Worker-Container führt asynchrone Aufgaben aus, die vom API-Container in die Warteschlange gestellt werden.

**Hauptkomponenten:**
- Celery Worker (tasks.py)
- Watchdog-Prozess zur Überwachung

## Deployment

Das Deployment erfolgt über die Digital Ocean App Platform und wird durch die `app.spec.yml` Datei konfiguriert.

### Kommunikation zwischen Containern

- Der Worker-Container verbindet sich über die private URL mit dem Redis-Server im API-Container
- Die Verbindungsdetails werden automatisch von Digital Ocean konfiguriert

## Lokale Entwicklung

Für die lokale Entwicklung kann man die Anwendung auf zwei Arten starten:

1. **Als einen einzelnen Container:** 
   ```
   cd backend
   make run
   ```

2. **Als getrennte Container:**
   ```
   cd backend
   make run-api     # Startet den API-Container
   make run-worker  # Startet den Worker-Container
   ```

## Konfiguration

Die Konfiguration erfolgt über Umgebungsvariablen, die in .env-Dateien definiert werden können. Beispiele finden sich in `.env.example`.

## Weitere Informationen

Weitere Informationen zum Digital Ocean-Deployment finden Sie in der Datei `DIGITALOCEAN.md`. 