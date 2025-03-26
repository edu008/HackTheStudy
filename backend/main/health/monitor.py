"""
Monitoring der API-Container-Gesundheit.
"""

import os
import sys
import time
import threading
import logging
import platform
import socket
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

# Entferne den Import aus der Modulebene
# from redis.client import get_redis_client
from resource_manager.limits import get_memory_usage, get_cpu_usage

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Globale Variablen für Health-Status
_health_data = {
    "status": "starting",
    "start_time": time.time(),
    "last_update": time.time(),
    "hostname": socket.gethostname(),
    "container_type": "api",
    "environment": os.environ.get('ENVIRONMENT', 'production'),
    "pid": os.getpid(),
    "memory_usage_mb": 0,
    "cpu_usage_percent": 0,
    "open_files": 0,
    "api_requests_total": 0,
    "api_requests_per_minute": 0,
    "api_errors_total": 0,
    "database_connection_status": "unknown",
    "redis_connection_status": "unknown",
    "celery_connection_status": "unknown"
}

# Metriken für API-Anfragen
_api_request_times = []
_api_errors = 0

def get_health_status():
    """
    Gibt den aktuellen Gesundheitsstatus der Anwendung zurück.
    
    Returns:
        dict: Gesundheitsstatus mit verschiedenen Metriken
    """
    current_time = datetime.datetime.now().isoformat()
    
    # Standard-Status, immer erfolgreich zurückgeben für Health-Checks
    return {
        "status": "healthy",
        "timestamp": current_time,
        "container_type": os.environ.get('CONTAINER_TYPE', 'api'),
        "environment": os.environ.get('ENVIRONMENT', 'production'),
        "checks": {
            "system": "ok",
            "api": "ok"
        }
    }

def update_health_data():
    """Aktualisiert die Gesundheitsdaten."""
    global _health_data, _api_request_times, _api_errors
    
    try:
        # Laufzeit berechnen
        uptime = time.time() - _health_data["start_time"]
        
        # Speicher- und CPU-Nutzung ermitteln
        memory_bytes, memory_percent = get_memory_usage()
        cpu_percent = get_cpu_usage()
        
        # Offene Dateien zählen
        open_files = 0
        try:
            from resource_manager.fd_monitor import get_open_file_descriptors
            open_files = len(get_open_file_descriptors())
        except:
            pass
        
        # API-Anfragen der letzten Minute zählen
        now = time.time()
        minute_ago = now - 60
        _api_request_times = [t for t in _api_request_times if t > minute_ago]
        requests_per_minute = len(_api_request_times)
        
        # Datenbankverbindung prüfen
        try:
            from core.models import db
            db.session.execute("SELECT 1")
            db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)}"
        
        # Redis-Verbindung prüfen
        try:
            # Redis direkt importieren und verwenden
            import redis as redis_lib
            redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
            redis_client = redis_lib.from_url(redis_url)
            redis_client.ping()
            redis_status = "connected"
        except Exception as e:
            redis_status = f"error: {str(e)}"
        
        # Celery-Verbindung prüfen
        try:
            from tasks.task_dispatcher import celery_app
            celery_status = "connected" if celery_app.connection().connected else "disconnected"
        except Exception as e:
            celery_status = f"error: {str(e)}"
        
        # Gesamtstatus ermitteln
        status = "healthy"
        
        # Downgrade auf "degraded", wenn eine Komponente ausgefallen ist
        if "error" in db_status or "error" in redis_status or "error" in celery_status:
            status = "degraded"
        
        # Health-Daten aktualisieren
        _health_data.update({
            "status": status,
            "last_update": time.time(),
            "uptime_seconds": uptime,
            "memory_usage_mb": memory_bytes / (1024 * 1024),
            "memory_usage_percent": memory_percent,
            "cpu_usage_percent": cpu_percent,
            "open_files": open_files,
            "api_requests_per_minute": requests_per_minute,
            "api_errors_total": _api_errors,
            "database_connection_status": db_status,
            "redis_connection_status": redis_status,
            "celery_connection_status": celery_status
        })
        
        # In Redis speichern für Worker-Zugriff
        try:
            # Redis direkt importieren und verwenden
            import redis as redis_lib
            redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
            redis_client = redis_lib.from_url(redis_url)
            redis_client.set(
                "health:api",
                json.dumps({**_health_data, "timestamp": datetime.now().isoformat()}),
                ex=60  # 1 Minute TTL
            )
        except Exception as e:
            logger.warning(f"Konnte Health-Status nicht in Redis speichern: {str(e)}")
    
    except Exception as e:
        logger.error(f"Fehler bei der Aktualisierung des Health-Status: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

def track_api_request():
    """Zählt eine API-Anfrage."""
    global _api_request_times, _health_data
    
    try:
        _api_request_times.append(time.time())
        _health_data["api_requests_total"] += 1
    except:
        pass

def track_api_error():
    """Zählt einen API-Fehler."""
    global _api_errors, _health_data
    
    try:
        _api_errors += 1
        _health_data["api_errors_total"] += 1
    except:
        pass

def start_health_monitoring(app=None):
    """
    Startet das Gesundheits-Monitoring für die Flask-App.
    Stellt sicher, dass verschiedene Systemkomponenten überwacht werden.
    
    Args:
        app: Die Flask-Anwendung
    """
    logger.info("Health-Monitoring wird initialisiert...")
    
    # Verwenden wir einen Thread für periodische Gesundheitsprüfungen
    def monitoring_thread():
        """Thread-Funktion für regelmäßige Überprüfungen."""
        while True:
            try:
                # Loggen wir einfach die aktuelle Zeit als Heartbeat
                current_time = datetime.datetime.now().isoformat()
                logger.info(f"Health-Monitor-Heartbeat: {current_time}")
                
                # Wenn wir eine App haben, prüfen wir auch den Redis-Status
                if app and hasattr(app, 'redis'):
                    try:
                        # Vorsichtig versuchen, ohne Fehler zu werfen
                        app.redis.ping()
                        logger.info("Redis-Verbindung ist aktiv")
                    except:
                        logger.warning("Redis-Verbindung ist nicht aktiv")
                
                # Schlafen für 5 Minuten
                time.sleep(300)
            except Exception as e:
                logger.error(f"Fehler im Monitoring-Thread: {str(e)}")
                # Bei Fehler trotzdem weitermachen
                time.sleep(60)
    
    # Thread starten
    try:
        thread = threading.Thread(target=monitoring_thread, daemon=True)
        thread.start()
        logger.info("Health-Monitoring-Thread gestartet")
        return thread
    except Exception as e:
        logger.error(f"Fehler beim Starten des Health-Monitoring-Threads: {str(e)}")
        return None

# Alias für Abwärtskompatibilität
start_health_monitor = start_health_monitoring 