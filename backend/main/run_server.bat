@echo off
REM Skript zum Starten der Flask-App mit Gunicorn/Waitress unter Windows

REM Setze Umgebungsvariablen
set PORT=8080
set FLASK_APP=app.py
set FLASK_DEBUG=1
set LOG_LEVEL=INFO
set PYTHONUNBUFFERED=1
set REDIS_URL=redis://localhost:6379/0

echo Starte HackTheStudy Backend API...
echo.
echo Umgebungsvariablen:
echo PORT=%PORT%
echo FLASK_APP=%FLASK_APP%
echo FLASK_DEBUG=%FLASK_DEBUG%
echo.

REM Prüfe, ob benötigte Pakete installiert sind
pip show waitress >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Waitress ist nicht installiert. Installiere Waitress...
    pip install waitress
    if %ERRORLEVEL% neq 0 (
        echo Fehler bei der Installation von Waitress.
        exit /b 1
    )
)

REM Installiere auch Gunicorn und Gevent (für Kompatibilität mit Deployment)
pip show gunicorn >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Installiere Gunicorn und Gevent für das Deployment...
    pip install gunicorn>=21.2.0 gevent>=23.9.1
)

REM Starte den Server mit dem Python-Skript
python run_gunicorn.py

echo.
echo Server beendet.
pause 