# HackTheStudy Backend

Dieses Repository enthält den Backend-Code für HackTheStudy, eine Lernplattform, die KI-gestützte Lernhilfen und intelligente Dokumentenverarbeitung bietet.

## Architektur

Das Backend besteht aus einer modularen Flask-Anwendung mit folgenden Hauptkomponenten:

### Kernkomponenten

- **app.py**: Hauptanwendungsdatei, die die Flask-App initialisiert und grundlegende Endpunkte definiert
- **config/**: Zentrale Konfigurationsverwaltung mit Unterstützung für verschiedene Umgebungen
- **bootstrap/**: App-Initialisierung, Erweiterungen und System-Patches
- **core/**: Kernmodelle und -funktionalitäten (Datenbankmodelle, Redis-Client, OpenAI-Integration)
- **api/**: REST-API-Endpunkte und Controller
- **openaicache/**: Implementierung für OpenAI-Caching und Token-Tracking
- **health/**: Gesundheitsprüfungen und Monitoring
- **utils/**: Allgemeine Hilfsfunktionen
- **tasks.py**: Hintergrundaufgaben und Worker-Kommunikation
- **resources.py**: Systemressourcenverwaltung

### API-Module

Die API wurde in spezialisierte Module aufgeteilt, die jeweils einen bestimmten Funktionsbereich abdecken:

- **api/auth/**: Benutzerauthentifizierung und -autorisierung
- **api/admin/**: Administrative Funktionen
- **api/uploads/**: Datei-Upload und -Verarbeitung
- **api/utils/**: Allgemeine Hilfsfunktionen
- **api/topics/**: Themen- und Inhaltsstrukturierung
- **api/questions/**: Fragemanagement und -generierung
- **api/flashcards/**: Karteikartensystem
- **api/finance/**: Zahlungsabwicklung und Kreditsystem

## Hauptfunktionen

### Benutzerauthentifizierung

- **JWT-basierte Authentifizierung**: Sichere Benutzerauthentifizierung mit JWT-Tokens
- **OAuth-Integration**: Unterstützung für externe Authentifizierungsanbieter
- **Berechtigungsverwaltung**: Feingranulare Zugriffssteuerung

### Dokumentenverarbeitung

- **Hochladen verschiedener Dateiformate**: Unterstützung für PDF, DOCX, TXT und mehr
- **Chunked Uploads**: Effiziente Handhabung großer Dateien durch Chunk-basierte Uploads
- **Textextraktion**: Automatische Extraktion von Text aus verschiedenen Dokumentformaten
- **Sessionmanagement**: Verwaltung von Upload-Sessions zur Gewährleistung der Datenkonsistenz

### KI-Integration

- **OpenAI-API-Integration**: Anbindung an OpenAI-Modelle für verschiedene KI-gestützte Funktionen
- **Token-Tracking**: Überwachung und Optimierung der Token-Nutzung
- **Caching-Mechanismus**: Effizienzsteigerung durch Caching von OpenAI-Anfragen

### Lernmaterial-Generierung

- **Themenextraktion**: Automatische Identifikation von Hauptthemen aus hochgeladenen Dokumenten
- **Fragen- und Quizgenerierung**: KI-gestützte Erstellung von Testfragen
- **Karteikartengenerierung**: Erstellung von Lernkarten auf Basis des Dokumenteninhalts
- **Spaced-Repetition-Algorithmen**: Intelligente Wiederholungsplanung für optimales Lernen

### Systemverwaltung und Monitoring

- **Health Checks**: Umfassende Gesundheitsprüfungen für alle Systemkomponenten
- **Ressourcenüberwachung**: Monitoring von Systemressourcen (CPU, Speicher, Datenbank)
- **Verbindungsüberwachung**: Überwachung der Verbindungen zu externen Diensten (Redis, Datenbank)

### Zahlungsintegration

- **Kreditsystem**: Management von Benutzerkredit für KI-gestützte Funktionen
- **Stripe-Integration**: Sichere Zahlungsabwicklung über Stripe
- **Abonnementmanagement**: Verwaltung von Benutzerabonnements

## Technologiestack

- **Webframework**: Flask 2.3.3
- **Datenbank**: PostgreSQL mit SQLAlchemy
- **Caching**: Redis
- **AI**: OpenAI API
- **Authentifizierung**: JWT, OAuth
- **Deployment**: Docker, DigitalOcean App Platform
- **Background Jobs**: Celery
- **Monitoring**: Prometheus, Health Checks

## Docker-Aufbau

Der Backend-Service wird als Docker-Container bereitgestellt und umfasst:

- Python 3.10 als Basisimage
- Redis-Server für Caching und Session-Verwaltung
- Gunicorn als WSGI-Server
- Health-Check-Endpunkte für Container-Orchestrierung

## Entwicklung

### Voraussetzungen

- Python 3.10+
- PostgreSQL
- Redis
- OpenAI API-Schlüssel

### Installation

1. Repository klonen
2. Abhängigkeiten installieren: `pip install -r requirements.txt`
3. `.env`-Datei auf Basis der `.env.example` erstellen
4. Anwendung starten: `python app.py`

## API-Dokumentation

Die API unterstützt verschiedene Endpunkte für:

- Benutzerauthentifizierung
- Dokumenten-Upload und -Verarbeitung
- Lernmaterial-Generierung und -Verwaltung
- Admin-Funktionen
- Health-Checks
