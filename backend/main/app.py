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

# Führe die Anwendung aus, wenn diese Datei direkt aufgerufen wird
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))