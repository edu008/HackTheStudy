# HackTheStudy Funktionsdokumentation

Dieses Dokument beschreibt die zentralen Funktionen des HackTheStudy-Systems nach der Optimierung. Es fokussiert sich auf die Backend- und Worker-Komponenten.

## Inhaltsverzeichnis

1. [Upload und Dateiverwaltung](#upload-und-dateiverwaltung)
2. [Dokumentenverarbeitung](#dokumentenverarbeitung)
3. [KI-Generierung](#ki-generierung)
4. [Session-Management](#session-management)
5. [Benutzerauthentifizierung](#benutzerauthentifizierung)

## Upload und Dateiverwaltung

### Direkter Datei-Upload

**Funktion**: `upload_file(request)` in `backend/main/api/uploads/upload.py`

Ermöglicht den direkten Upload von Dateien in das System. Die Datei wird als binäre Daten in der Upload-Tabelle gespeichert.

**Optimierungen**:
- Direkte Speicherung als Binärdaten in `file_content_1` statt als extrahierter Text
- Entfernung der Textextraktionsschritte für bessere Leistung

### Chunk-basierter Upload

**Funktion**: `upload_chunk()` in `backend/main/api/uploads/upload_chunked.py`

Ermöglicht den Upload großer Dateien in Chunks (Teilen).

**Optimierungen**:
- Eliminierung der ChunkedUpload-Tabelle
- Direkte Speicherung der Chunks in `Upload.file_content_1`
- Redis-basierte Fortschrittsverfolgung für bessere Performance

### Upload-Fortschritt

**Funktion**: `get_upload_progress(session_id)` in `backend/main/api/uploads/upload_chunked.py` 

Bietet Echtzeit-Statusinformationen während des Chunk-Uploads.

### Direkte Dateiverwendung

**Funktionen** in `backend/main/utils/direct_file_handling.py`:
- `save_file_for_processing(file_content, filename)`: Temporäre Speicherung für Verarbeitung
- `cleanup_temp_file(temp_path)`: Sichere Entfernung temporärer Dateien
- `extract_text_from_temp_file(temp_path)`: Bedarfsweise Textextraktion (Legacy-Support)

## Dokumentenverarbeitung

### Verarbeitungs-Initiierung

**Funktion**: `process_uploaded_file(upload_id, file_path, session_id, ...)` in `backend/main/api/uploads/processing.py`

Initiiert die Verarbeitung einer hochgeladenen Datei.

**Optimierungen**:
- Direkte Verwendung der Binärdaten statt Textextraktion
- Vereinfachter Prozessablauf ohne redundante Schritte

### Worker-Task-Definitionen

**Funktionen** in `backend/worker/tasks/__init__.py` und `backend/worker/tasks/ai_tasks.py`:

- `process_upload(task_id, file_path, file_type, options)`: Hauptfunktion für Dokumentenverarbeitung
- `process_document(task_id, file_path, session_id, task_metadata)`: Verarbeitet ein Dokument basierend auf einem ProcessingTask

**Optimierungen**:
- Entfernung der Textextraktions-Pipeline
- Direkte Verarbeitung der Binärdaten aus der Datenbank
- Synchrone API-Implementierung für bessere Stabilität

## KI-Generierung

### Themenextraktion

**Funktion**: `extract_topics(upload_id, max_topics, language, options)` in `backend/worker/tasks/ai_tasks.py`

Extrahiert Hauptthemen und Unterkonzepte aus einem Dokument.

**Optimierungen**:
- Direkte Verarbeitung aus Upload statt aus extrahiertem Text
- Synchrone OpenAI-API-Aufrufe statt asynchroner Wrapper
- Robuste Fehlerbehandlung mit Retry-Mechanismen

### Lernkartengenerierung

**Funktion**: `generate_flashcards(upload_id, num_cards, language, options)` in `backend/worker/tasks/ai_tasks.py`

Erstellt Lernkarten basierend auf dem Dokumenteninhalt.

**Optimierungen**:
- Direkte Dateiverarbeitung aus Upload
- Verbesserte PDF-Handhabung mit Vision-API-Unterstützung
- Vereinfachter Prozessablauf ohne Zwischenschritte

### Fragengenerierung

**Funktion**: `generate_questions(upload_id, num_questions, question_type, language, options)` in `backend/worker/tasks/ai_tasks.py`

Generiert Multiple-Choice- oder offene Fragen basierend auf dem Dokument.

**Optimierungen**:
- Direkte Dateiverarbeitung statt Textextraktion
- Synchrone API-Implementierung für bessere Fehlerbehandlung
- Verbesserte Fehlerbehandlung mit exponentieller Backoff-Strategie

### Direkte OpenAI-Aufrufe

**Funktionen** in `backend/worker/utils/ai_tools.py`:
- `call_openai_with_retry(prompt, model, temperature, ...)`: Wrapper mit Retry-Logik
- `extract_topics(content, max_topics, language, ...)`: Synchrone Themenextraktion 
- `generate_flashcards(content, num_cards, language, ...)`: Synchrone Lernkartengenerierung
- `generate_questions(content, num_questions, question_type, ...)`: Synchrone Fragengenerierung

**Optimierungen**:
- Entfernung unnötiger async/await-Wrapper
- Direkte synchrone API-Aufrufe für bessere Leistung

## Session-Management

### Session-Verwaltung

**Funktionen** in `backend/main/api/uploads/session_management.py`:
- `manage_user_sessions(user_id)`: Bereinigt alte Sessions eines Benutzers
- `update_session_timestamp(session_id)`: Aktualisiert den Zeitstempel einer aktiven Session
- `update_session_info(session_id, status, ...)`: Aktualisiert Session-Metadaten in Redis

### Direkte Dateisession-Aktualisierung

**Funktion**: `update_session_with_direct_file(session_id, upload_id)` in `backend/main/api/uploads/update_session_with_extracted_text.py`

Aktualisiert Session-Informationen mit der direkten Dateiverarbeitung.

**Optimierungen**:
- Ersatz für die veraltete `update_session_with_extracted_text`
- Direkte Verarbeitung ohne Textextraktion

## Benutzerauthentifizierung

### Token-Authentifizierung

**Funktion**: `token_required(f)` in `backend/main/api/auth.py`

Decorator für geschützte Routen, die Authentifizierung erfordern.

### Benutzerregistrierung und -anmeldung

**Funktionen** in `backend/main/api/auth.py`:
- `register_user()`: Registriert einen neuen Benutzer
- `login()`: Authentifiziert einen Benutzer und gibt ein Token zurück

## OpenAI API-Integration

### Direkte API-Aufrufe

**Funktion**: `call_openai_api(model, messages, temperature, max_tokens, **kwargs)` in `backend/worker/tasks/utils.py`

Führt direkte, synchrone Aufrufe an die OpenAI-API durch.

**Optimierungen**:
- Konvertierung von asynchronen zu synchronen API-Aufrufen
- Verbesserte Fehlerbehandlung und Logging
- Direkte Verarbeitung ohne unnötige Wrapper
