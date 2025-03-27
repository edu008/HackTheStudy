#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
HackTheStudy Backend API.
Hauptanwendungsdatei, definiert die Flask-App und Basis-Routen.
"""

# Importiere zuerst die Gevent-Konfiguration für Monkey-Patching
try:
    from bootstrap.system_patches import logger as patch_logger
    patch_logger.info("System-Patches in app.py importiert")
except ImportError:
    pass

import json
import logging
# System-Imports
import os
import signal
import sys
from datetime import datetime

from bootstrap.app_factory import create_app
from bootstrap.extensions import cache, cors, db, jwt, migrate
# Interne Imports - alle notwendigen Module am Anfang
from config.config import config
from flask import Flask, request
from health import (get_health_status, start_health_monitoring,
                    stop_health_monitoring, track_api_request)

# Stelle sicher, dass Verzeichnis-Struktur zum Pfad hinzugefügt wird
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Konfiguriere Logging sofort mit der vereinfachten zentralen Konfiguration
logger = config.setup_logging()

# Logge Basisinformationen für Debugging
logger.info("REDIS_URL: %s", config.redis_url)
logger.info("API_URL: %s", config.api_url)

# Erstelle die Flask-Anwendung mit der Factory
app = create_app()

# Die CORS-Konfiguration findet jetzt nur in app_factory.py statt

# Definiere die Health-Check-Endpunkte direkt in der app.py, um sicherzustellen, dass sie verfügbar sind


@app.route('/api/v1/simple-health', methods=['GET'])
def simple_health():
    """Einfacher Health-Check-Endpunkt für Docker/DigitalOcean Healthchecks."""
    track_api_request()
    logger.info("HEALTH-CHECK: Simple-Health-Anfrage empfangen von %s", request.remote_addr)
    return "ok", 200


@app.route('/health', methods=['GET'])
def health():
    """Allgemeiner Health-Check-Endpunkt."""
    track_api_request()
    logger.info("HEALTH-CHECK: Health-Anfrage empfangen von %s", request.remote_addr)
    return json.dumps(get_health_status()), 200, {'Content-Type': 'application/json'}


@app.route('/ping', methods=['GET'])
def ping():
    """Einfacher Ping-Endpunkt für Health-Checks."""
    track_api_request()
    logger.info("HEALTH-CHECK: Ping-Anfrage empfangen von %s", request.remote_addr)
    return "pong", 200


@app.route('/', methods=['GET'])
def root():
    """Root-Endpunkt"""
    track_api_request()
    logger.info("ROOT-Anfrage empfangen")
    return json.dumps({
        "status": "ok",
        "service": "HackTheStudy API",
        "timestamp": datetime.now().isoformat()
    })

# Signal-Handler für graceful shutdown


def signal_handler(sig, frame):
    """Signal-Handler für Shutdown-Signale."""
    logger.info("Signal empfangen, beende Anwendung...")
    # Alle Log-Handler leeren
    config.force_flush_handlers()
    stop_health_monitoring()
    sys.exit(0)


# Registriere Signal-Handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Starte Health-Monitoring
health_thread = start_health_monitoring(app)
logger.info("Health-Monitoring wurde gestartet")

# Führe die Anwendung aus, wenn diese Datei direkt aufgerufen wird
if __name__ == '__main__':
    # Verwende die Konfiguration aus dem zentralen Config-Objekt
    host = config.host
    app_port = config.port
    debug = config.debug

    logger.info("Starte API auf %s:%s, Debug-Modus: %s", host, app_port, debug)
    logger.info("Health-Check-Endpunkte verfügbar unter:")
    logger.info("  - http://%s:%s/api/v1/simple-health", host, app_port)
    logger.info("  - http://%s:%s/health", host, app_port)
    logger.info("  - http://%s:%s/ping", host, app_port)

    try:
        # Starte die Flask-Anwendung
        app.run(debug=debug, host=host, port=app_port, threaded=True, use_reloader=False)
    except Exception as e:
        logger.error("Fehler beim Starten der Anwendung: %s", e)
        sys.exit(1)
    finally:
        # Bei Beendigung Health-Monitoring stoppen
        stop_health_monitoring()
        # Log-Handler leeren
        config.force_flush_handlers()
