# Backend Worker Service (HackTheStudy)

## Übersicht

Dieser Service ist der Hintergrund-Worker für die HackTheStudy-Anwendung. Er ist verantwortlich für die Ausführung von zeitaufwändigen Aufgaben, insbesondere der Verarbeitung von hochgeladenen Dokumenten und der Interaktion mit der OpenAI-API, um Lernmaterialien zu generieren. Dadurch wird sichergestellt, dass der Haupt-API-Service (`main`) reaktionsschnell bleibt und nicht durch lange Operationen blockiert wird.

Der Worker wird als separater Docker-Container ausgeführt und verwendet Celery für die Aufgabenwarteschlange und -ausführung, wobei Redis als Nachrichtenbroker und Ergebnis-Backend dient.

## Architektur

**Komponenten & Interaktionen:**

1.  **Main API Container (`backend/main`):**
    *   Nimmt Uploads von Benutzern entgegen.
    *   Führt die Session-Management-Logik aus (max. Sessions pro User).
    *   Sendet einen `document.process_document`-Task über den Redis-Broker an den Worker.
2.  **Redis:**
    *   Dient als **Celery Broker**: Nimmt Tasks vom `main`-Container entgegen und stellt sie dem `worker`-Container zur Verfügung.
    *   Dient als **Celery Backend**: Speichert (optional) Task-Ergebnisse.
    *   Dient als **Cache**:\
        *   Speichert den extrahierten Text von Dokumenten (`extracted_text:{upload_id}`), um ihn nicht mehrfach über Task-Argumente senden zu müssen.
        *   Speichert Antworten von OpenAI-API-Aufrufen (`openai_cache:{task_type}:{hash}`), um wiederholte Anfragen zu vermeiden.
3.  **Worker Container (`backend/worker`):**
    *   Ein **Celery Worker**, der auf Tasks aus der Redis-Queue lauscht.
    *   Führt verschiedene Task-Typen aus (siehe unten).
    *   Interagiert mit der **PostgreSQL-Datenbank** zum Lesen von Upload-Daten und Speichern von generierten Ergebnissen (Lernkarten, Fragen, Themen).
    *   Ruft die externe **OpenAI-API** auf.
4.  **PostgreSQL Datenbank:**
    *   Die gemeinsame Datenbank, die von `main` und `worker` genutzt wird. Enthält Tabellen für `user`, `upload`, `flashcard`, `question`, `topic` etc.

## Kern-Workflow (Dokumentenverarbeitung)

1.  Der Worker erhält einen `document.process_document`-Task mit einer `upload_id`.
2.  Der Task holt das `Upload`-Objekt und den zugehörigen Dateiinhalt aus der Datenbank.
3.  Der Text wird aus dem Dokument extrahiert (abhängig vom Dateityp, z.B. PDF, DOCX).
4.  Der extrahierte Text wird in Redis gespeichert (`extracted_text:{upload_id}`).
5.  Eine **Celery Group** wird erstellt, um die AI-Generierungs-Tasks parallel zu starten:
    *   `ai.generate_flashcards`
    *   `ai.generate_questions`
    *   `ai.extract_topics`
6.  Jeder dieser AI-Tasks:
    *   Erhält die `upload_id`.
    *   Holt den extrahierten Text aus Redis.
    *   Prüft den OpenAI-Antwort-Cache in Redis.
    *   Ruft (falls kein Cache-Hit) die OpenAI-API mit spezifischen Prompts auf.
    *   Speichert die OpenAI-Antwort im Cache.
    *   Verarbeitet die Antwort und erstellt Datenbank-Objekte (z.B. `Flashcard`-Instanzen).
    *   Speichert die generierten Objekte effizient in der Datenbank (mit `add_all`).
7.  Nachdem alle Tasks der Gruppe (potenziell parallel) abgearbeitet wurden, ist die Verarbeitung für den Benutzer abgeschlossen.

## Wichtige Celery Tasks

*   **`document.process_document`**: Orchestriert die Verarbeitung eines Uploads (Textextraktion, Start der AI-Tasks).
*   **`ai.generate_flashcards`**: Ruft die Logik zur Generierung von Lernkarten auf und speichert sie.
*   **`ai.generate_questions`**: Ruft die Logik zur Generierung von Fragen auf und speichert sie.
*   **`ai.extract_topics`**: Ruft die Logik zur Extraktion von Themen auf und speichert sie.
*   **`maintenance.clean_temp_files`**: Bereinigt alte temporäre Dateien (periodisch auszuführen).
*   **`maintenance.clean_cache`**: Bereinigt alte Redis-Cache-Einträge (periodisch auszuführen).
*   **`maintenance.health_check`**: Führt einen System-Health-Check durch (periodisch auszuführen).

## Verzeichnisstruktur

*   **`app.py`**: Haupt-Einstiegspunkt, Celery-App-Konfiguration, Worker-Start.
*   **`tasks/`**: Enthält die Definitionen der Celery-Tasks.
    *   `__init__.py`: Registriert Tasks aus Untermodulen.
    *   `ai_tasks.py`: Definiert die AI-bezogenen Celery-Tasks und orchestriert deren Ablauf (DB-Speicherung etc.).
    *   `document_tasks.py`: Definiert den Dokumentenverarbeitungs-Task.
    *   `maintenance_tasks.py`: Definiert Wartungs-Tasks.
    *   `models.py`: SQLAlchemy-Modelldefinitionen (dupliziert von `main`, da separater Container).
    *   `flashcards/`, `questions/`, `topics/`: Enthalten die spezifische Logik (`generation.py`) für die Interaktion mit OpenAI für den jeweiligen Inhaltstyp (inkl. Prompting und Caching).
*   **`utils/`**: Allgemeine Hilfsfunktionen (OpenAI-API-Wrapper, Dateihandling, Textextraktion).
*   **`config/`**: Konfigurationslogik (`config.py`) und OpenAI-Prompts (`prompts.py`).
*   **`redis_utils/`**: Hilfsfunktionen für die Redis-Verbindung.
*   **`health/`**: Code für den Health-Check-Endpunkt.
*   **`Dockerfile`**: Anweisungen zum Bauen des Docker-Images für den Worker.
*   **`requirements.txt`**: Python-Abhängigkeiten des Workers (bereinigt).
*   **`.env`**: Umgebungsvariablen für lokale Entwicklung (Datenbank-URL, Redis-URL, OpenAI Key, Worker Concurrency etc.).

## Konfiguration

Die Konfiguration erfolgt hauptsächlich über Umgebungsvariablen, die in der `.env`-Datei (für lokale Entwicklung) oder über die Deployment-Umgebung gesetzt werden. Wichtige Variablen sind:

*   `DATABASE_URL`: Verbindungsstring zur PostgreSQL-Datenbank.
*   `REDIS_URL`: URL zum Redis-Server (Broker und Cache).
*   `REDIS_PASSWORD`: Passwort für Redis.
*   `OPENAI_API_KEY`: API-Schlüssel für OpenAI.
*   `WORKER_CONCURRENCY`: Anzahl der parallelen Prozesse für den Celery Worker (z.B. `4`).
*   `CELERY_...`: Diverse Celery-spezifische Einstellungen.
*   `LOG_LEVEL`: Detailgrad des Loggings (z.B. `INFO`, `DEBUG`).

## Worker Ausführen

1.  **Bauen:**
    ```bash
    docker build -t hackthestudy-worker -f backend/worker/Dockerfile .
    ```
2.  **Starten (Beispiel mit Docker Compose oder direkt):**
    ```bash
    # (Innerhalb von docker-compose.yml oder ähnlichem)
    docker run --env-file backend/worker/.env --network <dein_netzwerk> hackthestudy-worker
    ```
    Der Container startet `app.py`, welches dann den Celery Worker mit `celery_app.worker_main()` startet.

## Optimierungen

*   **Asynchronität:** Kernfunktionalität ist asynchron über Celery implementiert.
*   **Caching:** OpenAI-Antworten und extrahierter Text werden in Redis gecacht.
*   **Parallelisierung:** AI-Generierungs-Tasks werden als Gruppe parallel gestartet.
*   **Effizientes Speichern:** Datenbank-Objekte werden gesammelt mit `add_all` hinzugefügt.
*   **Code-Bereinigung:** Veraltete und redundante Code-Teile wurden entfernt.