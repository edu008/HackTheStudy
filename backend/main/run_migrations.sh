#!/bin/bash
# run_migrations.sh
# Führt Datenbankmigrationen im Container aus

set -e

echo "=== Starte Datenbankmigrationen ==="
echo "Datum: $(date)"

# Überprüfe, ob die Umgebungsvariablen gesetzt sind
if [ -z "$SQLALCHEMY_DATABASE_URI" ]; then
    echo "Warnung: SQLALCHEMY_DATABASE_URI ist nicht gesetzt"
    echo "Versuche, .env zu laden..."
    
    if [ -f ".env" ]; then
        echo "Lade Umgebungsvariablen aus .env"
        export $(grep -v '^#' .env | xargs)
    else
        echo "Keine .env-Datei gefunden."
    fi
fi

# Setze Python-Umgebungsvariablen
export PYTHONPATH=/app

# Führe die Migrationen aus
echo "Führe Migrationen aus..."
python /app/run_migrations.py

# Prüfe den Rückgabewert
if [ $? -eq 0 ]; then
    echo "✅ Migrationen erfolgreich abgeschlossen"
    exit 0
else
    echo "❌ Fehler bei der Ausführung der Migrationen"
    exit 1
fi 