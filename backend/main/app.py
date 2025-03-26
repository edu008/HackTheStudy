#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
HackTheStudy Backend API.
Hauptanwendungsdatei, definiert die Flask-App und Basis-Routen.
"""

# Importiere zuerst die Gevent-Konfiguration für Monkey-Patching
try:
    from bootstrap.gevent_config import logger as gevent_logger
    gevent_logger.info("Gevent-Konfiguration in app.py importiert")
except ImportError:
    pass

import os
import sys
import json
import logging
import signal
from datetime import datetime
from flask import Flask
from flask_cors import CORS

# Stelle sicher, dass Verzeichnis-Struktur zum Pfad hinzugefügt wird
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Importiere erst die Logging-Konfiguration
from bootstrap.logging_setup import setup_logging
# Konfiguriere Logging sofort
logger = setup_logging()

# Logge alle Umgebungsvariablen für Debugging-Zwecke
logger.info("=== UMGEBUNGSVARIABLEN FÜR MAIN-PROZESS (DigitalOcean) ===")
redis_vars = {}
digitalocean_vars = {}
app_vars = {}
celery_vars = {}

for key, value in os.environ.items():
    # Maskiere sensible Werte
    masked_value = value
    if any(sensitive in key.lower() for sensitive in ['key', 'secret', 'password', 'token']):
        masked_value = value[:4] + "****" if len(value) > 8 else "****"
    
    # Gruppiere nach Variablentyp
    if key.startswith("REDIS_") or "REDIS" in key:
        redis_vars[key] = masked_value
    elif "DIGITAL_OCEAN" in key or "DO_" in key or "PRIVATE_URL" in key:
        digitalocean_vars[key] = masked_value
    elif key.startswith("CELERY_"):
        celery_vars[key] = masked_value
    else:
        app_vars[key] = masked_value

# Logge die gruppierten Variablen
logger.info(f"REDIS-KONFIGURATION: {json.dumps(redis_vars, indent=2)}")
logger.info(f"DIGITALOCEAN-KONFIGURATION: {json.dumps(digitalocean_vars, indent=2)}")
logger.info(f"CELERY-KONFIGURATION: {json.dumps(celery_vars, indent=2)}")
logger.info(f"APP-KONFIGURATION: (Anzahl Variablen: {len(app_vars)})")
logger.info("=== ENDE UMGEBUNGSVARIABLEN ===")

# Prüfe explizit Redis-Verbindungsdetails
logger.info(f"REDIS_URL: {os.environ.get('REDIS_URL', 'nicht gesetzt')}")
logger.info(f"REDIS_HOST: {os.environ.get('REDIS_HOST', 'nicht gesetzt')}")
logger.info(f"API_HOST: {os.environ.get('API_HOST', 'nicht gesetzt')}")
logger.info(f"API.PRIVATE_URL oder ähnliche: {os.environ.get('api.PRIVATE_URL', os.environ.get('API_PRIVATE_URL', os.environ.get('PRIVATE_URL', 'nicht gesetzt')))}")

# Dann die App-Factory und Erweiterungen
from bootstrap.app_factory import create_app
from bootstrap.extensions import db, cache, migrate, jwt, cors

# Erstelle die Flask-Anwendung mit der Factory
app = create_app()

@app.route('/api/v1/simple-health', methods=['GET'])
def simple_health():
    """Einfacher Health-Check-Endpunkt für Docker/DigitalOcean Healthchecks"""
    logger.info(f"Simple-Health-Anfrage empfangen")
    return "ok", 200

@app.route('/ping', methods=['GET'])
def ping():
    """Einfacher Ping-Endpunkt für Health-Checks."""
    logger.info(f"Ping-Anfrage empfangen")
    return "pong", 200

@app.route('/', methods=['GET'])
def root():
    """Root-Endpunkt"""
    logger.info(f"ROOT-Anfrage empfangen von {os.environ.get('API_DOMAIN', 'lokal')}")
    return json.dumps({
        "status": "ok",
        "service": "HackTheStudy API",
        "timestamp": datetime.now().isoformat()
    })

# Signal-Handler für graceful shutdown
def signal_handler(sig, frame):
    logger.info("Signal empfangen, beende Anwendung...")
    sys.exit(0)

# Registriere Signal-Handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Führe die Anwendung aus, wenn diese Datei direkt aufgerufen wird
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))  # Stelle sicher, dass Port 8080 verwendet wird
    host = '0.0.0.0'  # Binde an alle Interfaces
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starte API auf {host}:{port}, Debug-Modus: {debug}")
    
    try:
        # Starte den Health-Monitor in einem separaten Thread
        try:
            from health_monitor import start_monitor_thread
            monitor_thread = start_monitor_thread()
            logger.info("Health-Monitor im Hintergrund gestartet")
        except (ImportError, AttributeError) as e:
            logger.warning(f"Health-Monitor konnte nicht gestartet werden: {e}")
        
        # Verwende Gunicorn für Produktionsumgebungen wenn möglich
        if os.environ.get('USE_GUNICORN', 'true').lower() == 'true':
            try:
                from gunicorn.app.wsgiapp import WSGIApplication
                
                # Gunicorn-Konfiguration als String
                gunicorn_conf = f"""
                bind = '{host}:{port}'
                workers = {os.environ.get('GUNICORN_WORKERS', '2')}
                worker_class = 'gevent'
                timeout = {os.environ.get('GUNICORN_TIMEOUT', '120')}
                keepalive = {os.environ.get('GUNICORN_KEEPALIVE', '5')}
                accesslog = '-'
                errorlog = '-'
                loglevel = 'info'
                """
                
                # Schreibe die Gunicorn-Konfiguration in eine temporäre Datei
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
                    f.write(gunicorn_conf)
                    conf_path = f.name
                
                logger.info(f"Starte Gunicorn mit Konfiguration: {conf_path}")
                
                # Starte Gunicorn mit der Konfiguration
                sys.argv = ['gunicorn', 'app:app', '-c', conf_path]
                WSGIApplication().run()
            except ImportError:
                logger.warning("Gunicorn nicht verfügbar, verwende Flask-Entwicklungsserver")
                app.run(debug=debug, host=host, port=port, threaded=True, use_reloader=False)
        else:
            # Starte die Flask-Anwendung mit dem Entwicklungsserver
            app.run(debug=debug, host=host, port=port, threaded=True, use_reloader=False)
    except Exception as e:
        logger.error(f"Fehler beim Starten der Anwendung: {e}")
        sys.exit(1)