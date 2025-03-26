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

# Stelle sicher, dass Verzeichnis-Struktur zum Pfad hinzugefügt wird
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Importiere erst die Logging-Konfiguration
from bootstrap.logging_setup import setup_logging
# Konfiguriere Logging sofort
logger = setup_logging()

# Dann die App-Factory und Erweiterungen
from bootstrap.app_factory import create_app
from bootstrap.extensions import db, cache, migrate, jwt, cors

# Erstelle die Flask-Anwendung
app = create_app()

# Die ping-Route ist bereits in app_factory.py definiert und muss hier nicht erneut angelegt werden

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
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
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
        
        # Starte die Flask-Anwendung
        app.run(debug=debug, host=host, port=port, threaded=True, use_reloader=False)
    except Exception as e:
        logger.error(f"Fehler beim Starten der Anwendung: {e}")
        sys.exit(1)