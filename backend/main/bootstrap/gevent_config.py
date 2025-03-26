"""
Gevent-Konfiguration für die Hauptanwendung.
Diese Datei sollte vor allen anderen Imports geladen werden.
"""

import logging

# Konfiguriere Logging vor dem Monkey-Patching
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gevent_config")

try:
    # Gevent-Monkey-Patching vor allen anderen Imports
    from gevent import monkey
    logger.info("Führe Gevent-Monkey-Patching durch...")
    
    # Alle relevanten Module patchen
    monkey.patch_all(
        socket=True,
        dns=True,
        time=True,
        select=True,
        thread=True,
        os=True,
        ssl=True,
        httplib=False,
        subprocess=True,
        sys=False,
        aggressive=True,
        Event=False
    )
    logger.info("Gevent-Monkey-Patching abgeschlossen")
except ImportError:
    logger.warning("Gevent nicht verfügbar - kein Monkey-Patching durchgeführt")
except Exception as e:
    logger.error(f"Fehler beim Gevent-Monkey-Patching: {str(e)}") 