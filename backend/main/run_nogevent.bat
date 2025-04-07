@echo off
REM Skript zum Starten der HackTheStudy-API ohne Gevent-Monkey-Patching

REM Setze wichtige Umgebungsvariablen
set GEVENT_MONKEY_PATCH=0
set PYTHONUNBUFFERED=1
set FLASK_APP=app.py
set FLASK_DEBUG=1
set PORT=8080

echo Starte HackTheStudy API ohne Gevent-Monkey-Patching...
echo Verwende sync Worker statt gevent Worker
echo.

REM Starte Gunicorn mit sync Worker
python -m gunicorn --worker-class=sync ^
                  --workers=2 ^
                  --threads=4 ^
                  --bind=0.0.0.0:%PORT% ^
                  --log-level=info ^
                  --access-logfile=- ^
                  --error-logfile=- ^
                  --timeout=120 ^
                  wsgi:application

pause 