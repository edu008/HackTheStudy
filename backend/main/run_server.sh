#!/bin/bash
# Skript zum Starten der Flask-App mit Gunicorn unter Linux/macOS

# Setze Umgebungsvariablen
export PORT=8080
export FLASK_APP=app.py
export FLASK_DEBUG=1
export LOG_LEVEL=INFO
export PYTHONUNBUFFERED=1
export REDIS_URL=redis://localhost:6379/0

echo "Starte HackTheStudy Backend API mit Gunicorn..."
echo
echo "Umgebungsvariablen:"
echo "PORT=$PORT"
echo "FLASK_APP=$FLASK_APP"
echo "FLASK_DEBUG=$FLASK_DEBUG"
echo

# Prüfe, ob Gunicorn installiert ist
if ! pip show gunicorn > /dev/null 2>&1; then
    echo "Gunicorn ist nicht installiert. Installiere Gunicorn..."
    pip install gunicorn>=21.2.0 gevent>=23.9.1
    if [ $? -ne 0 ]; then
        echo "Fehler bei der Installation von Gunicorn."
        exit 1
    fi
fi

# Stelle sicher, dass das Skript ausführbar ist
chmod +x run_gunicorn.py

# Starte den Server mit dem Python-Skript
python run_gunicorn.py

echo
echo "Server beendet." 