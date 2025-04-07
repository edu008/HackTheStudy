#!/bin/bash
# Skript zum Starten der HackTheStudy-API ohne Gevent-Monkey-Patching

# Setze wichtige Umgebungsvariablen
export GEVENT_MONKEY_PATCH=0
export PYTHONUNBUFFERED=1
export FLASK_APP=app.py
export FLASK_DEBUG=1
export PORT=8080

echo "Starte HackTheStudy API ohne Gevent-Monkey-Patching..."
echo "Verwende sync Worker statt gevent Worker"
echo ""

# Starte Gunicorn mit sync Worker
gunicorn --worker-class=sync \
         --workers=2 \
         --threads=4 \
         --bind=0.0.0.0:$PORT \
         --log-level=info \
         --access-logfile=- \
         --error-logfile=- \
         --timeout=120 \
         wsgi:application 