# Docker Logs Paket

Dieses Paket enthält alle Module und Funktionen für verbesserte Docker-Logs. Es sorgt für schönere, farbige Logs mit Emojis und optimierter Datenformatierung.

## 🌟 Hauptfunktionen

- 🎨 **Farbige Logs** mit Emojis für bessere Lesbarkeit
- 📊 **Daten-Zusammenfassung** statt vollständiger Ausgabe
- ⏱️ **Fortschrittsanzeigen** und Ladeanimationen
- 🔄 **Automatische Integration** in Flask und SQLAlchemy
- 🚀 **Banner und visuelle Elemente** für den Container-Start

## 🛠️ Verwendung

1. **Gesamtes Logging-System einrichten**:

```python
import docker_logs

# Richtet das gesamte Logging-System ein
docker_logs.setup_all_logging()

# Oder mit Flask-App
from flask import Flask
app = Flask(__name__)
docker_logs.setup_all_logging(app)
```

2. **Direkter Zugriff auf Logger**:

```python
from docker_logs import api_logger, db_logger, app_logger

# App-Events loggen
app_logger.info("Anwendung gestartet", extra={'emoji': '🚀'})

# API-Anfragen loggen
api_logger.info("GET /api/v1/users/123", extra={
    'data': {'params': {'id': 123}},
    'emoji': '🔍'
})

# DB-Abfragen loggen
db_logger.info("SELECT * FROM users", extra={
    'data': {'rows': 10},
    'emoji': '🗃️'
})
```

3. **Hilfreiche Logging-Funktionen**:

```python
from docker_logs import log_request_start, log_request_end, log_db_query

# API-Anfrage loggen
log_request_start("/api/v1/users", "GET")
# ... Verarbeitung ...
log_request_end("/api/v1/users", "GET", 200, 0.125)

# DB-Abfrage loggen
log_db_query("SELECT * FROM users WHERE id = ?", params=[123])
```

4. **Daten-Formatierung**:

```python
from docker_logs import format_dict_summary, format_list_summary

# Daten formatieren
user_data = {"id": 123, "name": "Test", "email": "test@example.com"}
print(format_dict_summary(user_data))

tasks = [{"id": 1, "name": "Task 1"}, {"id": 2, "name": "Task 2"}]
print(format_list_summary(tasks))
```

## 🧪 Testen

Das Testskript `test_logs.py` demonstriert alle Funktionen:

```bash
python test_logs.py
```

## 📂 Module

- **docker_banner.py**: ASCII-Banner und Ladeanimationen
- **docker_data_formatter.py**: Datenformatierung und Fortschrittsanzeigen
- **docker_logging_integration.py**: Flask- und API-Logging-Integration
- **db_log_patch.py**: SQLAlchemy-Integration für DB-Logs

## 🔧 Konfiguration

Konfiguriere das Logging über Umgebungsvariablen:

- `USE_COLORED_LOGS`: `true` um farbige Logs zu aktivieren
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING` oder `ERROR`
- `PYTHONUNBUFFERED`: `1` für unbuffered Output 