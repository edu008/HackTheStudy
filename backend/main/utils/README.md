# Utils-Modularisierung

Dieses Dokument erklärt die Struktur und Verwendung der Dienstprogramm-Module in der Anwendung.

## Modulstruktur

Die Anwendung verwendet zwei Hauptverzeichnisse für Hilfsfunktionen:

1. **`/utils/`** - Primäre Implementierung von Hilfsfunktionen:
   - `file_utils.py` - Dateiverarbeitung, -extraktion und -validierung
   - `validators.py` - Allgemeine Validierungsfunktionen
   - Weitere grundlegende Hilfsprogramme

2. **`/api/utils/`** - API-spezifische Hilfsfunktionen:
   - `ai_utils.py` - Funktionen für KI-Integration
   - `content_analysis.py` - Funktionen zur Inhaltsanalyse
   - `learning_materials.py` - Funktionen zur Generierung von Lernmaterialien
   - `session_utils.py` - Sitzungsverwaltung
   - `text_processing.py` - API-spezifische Textverarbeitungsfunktionen

## Richtlinien für die Verwendung

### Neue Funktionalität implementieren

- Allgemeine Hilfsfunktionen sollten in `/utils/` implementiert werden
- API-spezifische Funktionen sollten in `/api/utils/` implementiert werden
- Keine Duplikate zwischen den beiden Verzeichnissen erstellen
- Bevorzuge die Implementierungen im Hauptmodul (`/utils/`)

### Importieren von Funktionen

Die empfohlene Import-Hierarchie ist:

1. Zuerst aus der korrekten Modulebene importieren:
   ```python
   from utils.file_utils import extract_text_from_file
   ```

2. Bei API-spezifischen Funktionen:
   ```python
   from api.utils.ai_utils import generate_embeddings
   ```

3. Für API-Module, die Hauptfunktionen verwenden:
   ```python
   # In /api/utils/text_processing.py
   from utils.text_utils import clean_text_for_database
   ```

## Übergangsphase

Die aktuellen redundanten Implementierungen werden schrittweise konsolidiert:

- `api/utils/file_utils.py` reexportiert jetzt die Funktionen aus dem Hauptmodul
- Zukünftige Versionen könnten zu einer flacheren Struktur wechseln

## Fehlerbehandlung

Die Fehlerbehandlung wurde zentralisiert:
- `api/errors/` enthält das modulare Fehlerbehandlungssystem
- `api/error_handler.py` reexportiert Funktionen für Abwärtskompatibilität
- Verwende immer relative Imports für Fehlerbehandlung:
  ```python
  from ..error_handler import log_error
  ```

Diese Modularisierung trägt zur besseren Organisation, Wartbarkeit und Testbarkeit des Codes bei. 