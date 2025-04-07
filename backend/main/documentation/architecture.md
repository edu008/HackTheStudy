# HackTheStudy Systemarchitektur

## Überblick

HackTheStudy ist eine Anwendung zur Dokumentenverarbeitung und KI-gestützten Lernmaterialgenerierung. Die Plattform ermöglicht es Benutzern, Dokumente hochzuladen und mithilfe von künstlicher Intelligenz automatisch Lernkarten, Fragen und thematische Analysen zu erstellen.

Die Architektur besteht aus drei Hauptkomponenten:
1. **Frontend**: Benutzeroberfläche (nicht Teil dieser Dokumentation)
2. **Backend (Flask)**: API und Anfrageverarbeitung
3. **Worker (Celery)**: Aufgabenwarteschlange für KI-gestützte Dokumentenverarbeitung

## Systemkomponenten

### 1. Backend (Flask)

Das Backend ist eine Flask-Anwendung, die APIs für Datei-Uploads, Benutzerverwaltung und Lernmaterialzugriff bereitstellt. Zentrale Komponenten:

- **API-Endpoints**: REST-Schnittstellen für Client-Anwendungen
- **Datenbankmodelle**: SQLAlchemy-Modelle für Daten- und Beziehungsverwaltung
- **Authentifizierung**: Token-basierte Authentifizierung mit JWT
- **Upload-Management**: Direkter Datei-Upload mit Chunk-Support für große Dateien
- **Session-Management**: Verwaltung von Benutzersitzungen und zugehörigen Uploads

### 2. Worker (Celery)

Der Worker verwendet Celery für asynchrone Aufgabenverarbeitung und ist für die KI-gestützte Analyse zuständig:

- **Task Queue**: Redis-basierte Warteschlange für Verarbeitungsaufgaben
- **Dokumentenverarbeitung**: Direkte Verarbeitung von Dateien mit OpenAI-API
- **KI-Generierung**: Erzeugung von Lernkarten, Fragen und Themen
- **Fehlerbehandlung**: Retry-Mechanismen und robuste Fehlerbehandlung

### 3. Datenbank

PostgreSQL-Datenbank mit folgenden Haupttabellen:

- **User**: Benutzerinformationen und Authentifizierungsdaten
- **Upload**: Speichert Dokumente und Metadaten zu Uploads
- **Topic**: Themen aus der KI-Analyse
- **Flashcard**: Generierte Lernkarten
- **Question**: Generierte Fragen mit Antworten

## Datenfluss

1. **Dokument-Upload**:
   - Benutzer lädt ein Dokument über die Frontend-Schnittstelle hoch
   - Backend speichert die Datei direkt als Binärdaten in der Upload-Tabelle
   - Eine Session-ID und Upload-ID werden generiert

2. **Verarbeitung**:
   - Backend übergibt Verarbeitungsaufgaben an den Worker
   - Worker greift auf die Datei in der Datenbank zu und führt KI-Analysen durch
   - Ergebnisse werden in den entsprechenden Datenbanktabellen gespeichert

3. **Ergebnis-Abruf**:
   - Frontend fragt periodisch den Status der Verarbeitung ab
   - Nach Abschluss werden die generierten Materialien angezeigt

## Optimierte Bereiche

Die Architektur wurde in folgenden Bereichen optimiert:

1. **Direkte Dateiverarbeitung**:
   - Eliminierung der Textextraktionsschritte
   - Direkte Verwendung der Binärdateien in der Datenbank
   - Beseitigung redundanter Zwischenschritte

2. **Vereinfachtes Datenmodell**:
   - Entfernung der ChunkedUpload-Tabelle
   - Rationalisierung der Upload-Tabelle durch Entfernung redundanter Felder

3. **Effiziente API-Aufrufe**:
   - Synchrone Implementierung der OpenAI-API-Aufrufe
   - Entfernung unnötiger asynchroner Wrapper

4. **Verbesserte Fehlerbehandlung**:
   - Robuste Fehlerbehandlung mit exponentieller Backoff-Strategie
   - Detaillierte Fehlerprotokolle für Diagnose

## Technologiestack

- **Backend**: Python, Flask
- **API-Framework**: Flask-RESTful
- **Datenbank**: PostgreSQL, SQLAlchemy ORM
- **Warteschlange**: Redis, Celery
- **KI-Integration**: OpenAI API (GPT-4, GPT-3.5)
- **Authentifizierung**: JWT
- **Dateiverarbeitung**: Direkte Binärspeicherung

## Diagramm

```
+--------------------+     +--------------------+     +--------------------+
|                    |     |                    |     |                    |
|     Frontend       |---->|      Backend       |---->|      Worker        |
|                    |     |     (Flask)        |     |     (Celery)       |
+--------------------+     +--------------------+     +--------------------+
                                   |   ^                      |   ^
                                   v   |                      v   |
                           +--------------------+     +--------------------+
                           |                    |     |                    |
                           |     Datenbank      |<--->|     OpenAI API     |
                           |   (PostgreSQL)     |     |                    |
                           +--------------------+     +--------------------+
```
