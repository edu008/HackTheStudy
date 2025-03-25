#!/usr/bin/env python
"""
Eigenständiges Health-Monitoring-Skript für den API-Container.
Wird als separater Prozess neben dem Haupt-API-Server ausgeführt.
"""

import os
import sys
import time
import logging
import signal
import json
import threading
from datetime import datetime

# Initialisiere Logging
logging.basicConfig(
    level=logging.INFO,
    format='[HEALTH] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("health_monitor")

# Importiere Redis-Client
try:
    from redis.client import get_redis_client, safe_redis_set
    redis_client = get_redis_client()
    logger.info("Redis-Client erfolgreich initialisiert")
except ImportError:
    logger.error("Konnte Redis-Client nicht importieren, versuche direkte Redis-Import")
    try:
        import redis
        import json
        
        redis_client = redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))
        
        def safe_redis_set(key, value, ex=None, nx=False):
            try:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value)
                return redis_client.set(key, value, ex=ex, nx=nx)
            except Exception as e:
                logger.error(f"Fehler beim Schreiben in Redis: {str(e)}")
                return False
                
        logger.info("Redis-Client über Fallback-Methode initialisiert")
    except Exception as e:
        logger.error(f"Konnte Redis-Client nicht initialisieren: {str(e)}")
        redis_client = None
        def safe_redis_set(*args, **kwargs):
            logger.warning("Redis-Client nicht verfügbar, kein Datenzugriff möglich")
            return False

def main():
    """Hauptfunktion für das Health-Monitoring."""
    logger.info("Health-Monitor gestartet")
    
    # Für sauberes Herunterfahren
    stop_event = threading.Event()
    
    # Signalhandler für sauberes Herunterfahren
    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} empfangen, fahre herunter...")
        stop_event.set()
    
    # Signal-Handler registrieren
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Startzeitpunkt speichern
    start_time = time.time()
    
    # Health-Monitoring-Loop
    try:
        while not stop_event.is_set():
            try:
                # Prüfe Redis-Verbindung
                if redis_client:
                    redis_client.ping()
                    redis_ok = True
                else:
                    redis_ok = False
                
                # Health-Status in Redis speichern
                health_data = {
                    "status": "healthy" if redis_ok else "degraded",
                    "uptime": time.time() - start_time,
                    "timestamp": datetime.now().isoformat(),
                    "component": "health_monitor",
                    "redis_status": "connected" if redis_ok else "disconnected"
                }
                
                if redis_client:
                    safe_redis_set(
                        "health:monitor",
                        health_data,
                        ex=60  # 1 Minute TTL
                    )
                    
                logger.debug("Health-Check durchgeführt")
            except Exception as e:
                logger.error(f"Fehler im Health-Monitoring: {str(e)}")
            
            # Alle 30 Sekunden prüfen, mit Möglichkeit zum vorzeitigen Abbruch
            stop_event.wait(30)
    except KeyboardInterrupt:
        logger.info("Tastaturunterbrechung empfangen, fahre herunter...")
    except Exception as e:
        logger.error(f"Unerwarteter Fehler: {str(e)}")
    finally:
        logger.info("Health-Monitor wird beendet")

if __name__ == "__main__":
    main() 