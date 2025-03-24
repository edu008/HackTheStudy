# HackTheStudy: Digital Ocean Deployment Guide

Diese Dokumentation erklärt den Aufbau und das Deployment der HackTheStudy-Anwendung auf Digital Ocean mit einer Zwei-Container-Architektur.

## Architektur

Die Anwendung ist in zwei Container aufgeteilt:

1. **API-Container** - Enthält:
   - Flask API (Hauptanwendung)
   - Redis (für Zwischenspeicherung und Celery-Broker)
   - Gunicorn als WSGI-Server

2. **Worker-Container** - Enthält:
   - Celery Worker für asynchrone Aufgaben
   - Watchdog-Prozess zur Überwachung

Diese Trennung bietet mehrere Vorteile:
- Bessere Ressourcenisolierung
- Unabhängige Skalierung von API und Workern
- Verbesserte Stabilität durch klare Aufgabentrennung

## Dateien für das Deployment

Die folgenden Dateien sind für das Deployment relevant:

- `Dockerfile.api` - Dockerfile für den API-Container
- `Dockerfile.worker` - Dockerfile für den Worker-Container 
- `config/supervisor-api.conf` - Supervisor-Konfiguration für den API-Container
- `config/supervisor-worker.conf` - Supervisor-Konfiguration für den Worker-Container
- `app.spec.yml` - Digital Ocean App-Spezifikation

## Deployment-Schritte

### 1. Vorbereitung

- Stelle sicher, dass du ein Digital Ocean-Konto hast
- Verbinde dein GitHub-Repository mit Digital Ocean

### 2. App-Erstellung in Digital Ocean

1. Öffne die Digital Ocean App Platform
2. Wähle "Create App" und verbinde dein GitHub-Repository
3. Wähle den Branch "main" und die Source Directory "backend"
4. Wähle App Platform als Deployment-Option

### 3. App-Komponenten konfigurieren

Die App besteht aus zwei Komponenten:

#### API Component:
- Name: api
- Type: Web Service
- Source Directory: backend
- Dockerfile Path: backend/Dockerfile.api
- HTTP Port: 8080
- Instance Size: Basic S
- Instance Count: 1

#### Worker Component:
- Name: worker
- Type: Worker
- Source Directory: backend
- Dockerfile Path: backend/Dockerfile.worker
- Instance Size: Basic XS
- Instance Count: 1

### 4. Umgebungsvariablen einrichten

Folgende Umgebungsvariablen müssen als Secrets konfiguriert werden:

- `DATABASE_URL` - PostgreSQL-Verbindungsstring
- `JWT_SECRET` - Secret für JWT-Token
- `FLASK_SECRET_KEY` - Flask-Secret-Key
- `OPENAI_API_KEY` - OpenAI API-Schlüssel
- `STRIPE_API_KEY` - Stripe API-Schlüssel
- `STRIPE_WEBHOOK_SECRET` - Stripe Webhook-Secret
- `STRIPE_PUBLISHABLE_KEY` - Stripe öffentlicher Schlüssel
- OAuth-Schlüssel (Google, GitHub)

Die anderen Variablen werden automatisch aus der app.spec.yml-Datei geladen.

### 5. Domain konfigurieren

Konfiguriere die Domain `api.hackthestudy.ch` für den API-Service.

## Monitoring und Wartung

### Health Checks

- Der API-Container stellt den Endpunkt `/api/v1/health` bereit
- Digital Ocean überwacht diesen Endpunkt für automatische Neustarts

### Logs

- Container-Logs sind in der Digital Ocean-Konsole verfügbar
- Jeder Container hat ein spezifisches LOG_PREFIX für einfache Filterung:
  - `[API]` für den API-Container
  - `[WORKER]` für den Worker-Container

### Skalierung

Um die Anwendung zu skalieren:

1. Erhöhe die Instance Count für den API-Container für mehr Web-Kapazität
2. Erhöhe die Instance Count für den Worker-Container für mehr Verarbeitungskapazität

## Fehlerbehebung

### API-Container startet nicht

1. Prüfe die Logs auf Fehlermeldungen
2. Stelle sicher, dass die Datenbank erreichbar ist
3. Überprüfe die Umgebungsvariablen

### Worker-Container startet nicht

1. Prüfe die Logs auf Fehlermeldungen
2. Stelle sicher, dass der Redis-Service im API-Container läuft
3. Überprüfe die REDIS_URL-Umgebungsvariable

### Sonstige Probleme

Bei anderen Problemen:

1. Prüfe die Health-Check-Endpunkte
2. Analysiere die Container-Logs
3. Starte die Container neu, wenn nötig 