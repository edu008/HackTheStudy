#!/bin/bash
# Skript zum Einrichten und Testen der PyLint-Integration

# Zum Backend-Verzeichnis wechseln, falls das Skript von einem anderen Verzeichnis aufgerufen wird
cd "$(dirname "$0")"

echo "=== Einrichtung der PyLint-Integration ==="
echo ""

# Ausführungsrechte für das Linting-Skript setzen
chmod +x lint.py
echo "✅ Ausführungsrechte für lint.py gesetzt"

# Prüfen, ob PyLint und autopep8 installiert sind
echo "Prüfe, ob PyLint und autopep8 installiert sind..."
PYLINT_INSTALLED=$(pip list | grep -i pylint || echo "")
AUTOPEP8_INSTALLED=$(pip list | grep -i autopep8 || echo "")

if [ -z "$PYLINT_INSTALLED" ]; then
    echo "⚠️ PyLint ist nicht installiert. Installiere es mit:"
    echo "   pip install pylint==2.17.5"
else
    echo "✅ PyLint ist installiert: $PYLINT_INSTALLED"
fi

if [ -z "$AUTOPEP8_INSTALLED" ]; then
    echo "⚠️ autopep8 ist nicht installiert. Installiere es mit:"
    echo "   pip install autopep8==2.0.4"
else
    echo "✅ autopep8 ist installiert: $AUTOPEP8_INSTALLED"
fi

echo ""
echo "=== PyLint-Konfiguration ==="
echo "Die Konfigurationsdatei befindet sich in: $(pwd)/pylintrc"
echo ""

echo "=== Test-Linting ==="
echo "Du kannst das Linting-Skript jetzt testen mit:"
echo "  ./lint.py"
echo "  ./lint.py --path main/app.py"
echo "  ./lint.py --fix --path worker/"
echo ""

echo "=== Dokumentation ==="
echo "Eine detaillierte Dokumentation zur Verwendung von PyLint findest du in:"
echo "  $(pwd)/LINTING.md"
echo ""

echo "=== Fertig ==="
echo "Die PyLint-Integration wurde erfolgreich eingerichtet." 