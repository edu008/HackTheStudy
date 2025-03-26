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
from flask import Flask, request
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

# Definiere die Health-Check-Endpunkte direkt in der app.py, um sicherzustellen, dass sie verfügbar sind
@app.route('/api/v1/simple-health', methods=['GET'])
def simple_health():
    """Einfacher Health-Check-Endpunkt für Docker/DigitalOcean Healthchecks."""
    logger.info(f"HEALTH-CHECK: Simple-Health-Anfrage empfangen von {request.remote_addr}")
    print(f"DIREKT-PRINT: Simple-Health-Anfrage empfangen von {request.remote_addr}", flush=True)
    return "ok", 200

@app.route('/health', methods=['GET'])
def health():
    """Allgemeiner Health-Check-Endpunkt."""
    logger.info(f"HEALTH-CHECK: Health-Anfrage empfangen von {request.remote_addr}")
    print(f"DIREKT-PRINT: Health-Anfrage empfangen von {request.remote_addr}", flush=True)
    return "healthy", 200

@app.route('/ping', methods=['GET'])
def ping():
    """Einfacher Ping-Endpunkt für Health-Checks."""
    logger.info(f"HEALTH-CHECK: Ping-Anfrage empfangen von {request.remote_addr}")
    print(f"DIREKT-PRINT: Ping-Anfrage empfangen von {request.remote_addr}", flush=True)
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
    # Verwende Port 8080 für die Flask-App mit integrierten Health-Checks
    app_port = int(os.environ.get('APP_PORT', 8080))  # Flask-App auf 8080
    # Binde an ALLE Netzwerk-Interfaces (0.0.0.0)
    host = '0.0.0.0'
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    logger.info(f"Starte API auf {host}:{app_port}, Debug-Modus: {debug}")
    logger.info(f"Health-Check-Endpunkte verfügbar unter:")
    logger.info(f"  - http://{host}:{app_port}/api/v1/simple-health")
    logger.info(f"  - http://{host}:{app_port}/health")
    logger.info(f"  - http://{host}:{app_port}/ping")
    
    try:
        # Starte die Flask-Anwendung auf Port 8080
        app.run(debug=debug, host=host, port=app_port, threaded=True, use_reloader=False)
    except Exception as e:
        logger.error(f"Fehler beim Starten der Anwendung: {e}")
        sys.exit(1)