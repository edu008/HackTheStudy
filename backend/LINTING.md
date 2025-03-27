# Code-Qualitätsprüfung mit PyLint

Dieses Dokument beschreibt, wie du PyLint zur Code-Qualitätsprüfung im HackTheStudy-Backend verwenden kannst.

## Installation

PyLint und autopep8 (für automatische Korrekturen) sind bereits in den `requirements.txt`-Dateien enthalten. Stelle sicher, dass du deine virtuelle Umgebung mit den aktuellen Abhängigkeiten aktualisiert hast:

```bash
# Im main-Verzeichnis
pip install -r requirements.txt

# Oder im worker-Verzeichnis
pip install -r requirements.txt
```

## Verwendung des Linting-Skripts

Das Projekt enthält ein praktisches Skript (`lint.py`), das PyLint mit der konfigurierten `pylintrc`-Datei ausführt:

```bash
# Im backend-Verzeichnis
python lint.py

# Nur ein bestimmtes Modul oder eine bestimmte Datei prüfen
python lint.py --path main/app.py
python lint.py --path worker/

# Detaillierte Fehlerinformationen anzeigen
python lint.py --details

# Automatische Korrekturen mit autopep8 durchführen
python lint.py --fix

# Einen anderen Schwellenwert für die Bewertung festlegen (0-10, Standard: 7.0)
python lint.py --threshold 8.0
```

## Direkte Verwendung von PyLint

Du kannst PyLint auch direkt aufrufen:

```bash
# Im backend-Verzeichnis
pylint --rcfile=pylintrc main/
pylint --rcfile=pylintrc worker/
```

## Konfiguration

Die PyLint-Konfiguration befindet sich in der Datei `backend/pylintrc`. Diese Konfiguration enthält folgende Anpassungen:

- Erweiterte Zeilenlänge (120 Zeichen)
- Deaktivierte Warnungen für häufige false positives
- Angepasste Benennungskonventionen
- Ignorierte Verzeichnisse und Dateien
- Konfiguration für Flask- und SQLAlchemy-spezifische Probleme

## Automatische Code-Formatierung

Das Linting-Skript bietet mit der Option `--fix` automatische Formatierungskorrekturen mit autopep8:

```bash
python lint.py --fix
```

Dies führt folgende Aktionen aus:
- Korrigiert Einrückungen
- Entfernt unnötige Whitespaces
- Korrigiert Importreihenfolge
- Behebt einfache PEP 8-Stilprobleme

## Integration in die Entwicklungsumgebung

### VS Code

Für Visual Studio Code kannst du PyLint als Linter aktivieren, indem du folgende Einstellungen zu deiner `.vscode/settings.json`-Datei hinzufügst:

```json
{
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "python.linting.pylintPath": "pylint",
    "python.linting.pylintArgs": [
        "--rcfile=${workspaceFolder}/backend/pylintrc"
    ]
}
```

### PyCharm

Für PyCharm:
1. Gehe zu `File > Settings > Tools > External Tools`
2. Klicke auf `+` und füge ein neues Tool hinzu:
   - Name: PyLint
   - Program: Der Pfad zu deinem PyLint (z.B. `$PyInterpreterDirectory$/pylint`)
   - Arguments: `--rcfile=$ProjectFileDir$/backend/pylintrc $FileDir$/$FileName$`
   - Working directory: `$ProjectFileDir$`

## Best Practices

- Führe das Linting regelmäßig während der Entwicklung aus, nicht erst am Ende
- Verwende `--fix`, um einfache Probleme automatisch zu beheben
- Ignoriere keine Warnungen ohne guten Grund
- Aktualisiere die pylintrc-Datei bei Bedarf, um sie an Projektanforderungen anzupassen

## Häufige Linting-Probleme und Lösungen

### Zu lange Zeilen
```python
# Schlecht
result = do_something_complex(first_parameter, second_parameter, third_parameter) + another_complex_function(fourth_parameter)

# Besser
result = (do_something_complex(first_parameter, second_parameter, third_parameter) + 
          another_complex_function(fourth_parameter))
```

### Zu viele lokale Variablen
```python
# Schlecht: Zu viele lokale Variablen in einer Funktion
def process_data():
    var1 = ...
    var2 = ...
    # ... viele weitere Variablen ...
    
# Besser: In kleinere Funktionen aufteilen
def process_data():
    part1 = process_part1()
    part2 = process_part2()
    return combine_results(part1, part2)
```

### Ungenutzte Importe
```python
# Schlecht: Ungenutzte Importe
import os
import sys
import json  # Wird nicht verwendet

# Besser: Nur verwendete Module importieren
import os
import sys
``` 