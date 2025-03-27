"""
Basis-Funktionalität für das Health-Monitoring-System.
Enthält grundlegende Datenstrukturen und Statusverwaltung.
"""

import os
import time
import logging
import socket
import json
from datetime import datetime
from typing import Dict, Any

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Globale Variablen für Health-Status
_health_data = {
    "status": "starting",
    "start_time": time.time(),
    "last_update": time.time(),
    "hostname": socket.gethostname(),
    "container_type": os.environ.get('CONTAINER_TYPE', 'api'),
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
    global _health_data
    
    # Kopie erstellen, damit die Originaldaten nicht verändert werden
    current_data = _health_data.copy()
    current_data["timestamp"] = datetime.now().isoformat()
    
    return current_data

def track_api_request():
    """Zählt eine API-Anfrage."""
    global _api_request_times, _health_data
    
    try:
        _api_request_times.append(time.time())
        _health_data["api_requests_total"] += 1
    except Exception as e:
        logger.error(f"Fehler beim Tracking einer API-Anfrage: {str(e)}")

def track_api_error():
    """Zählt einen API-Fehler."""
    global _api_errors, _health_data
    
    try:
        _api_errors += 1
        _health_data["api_errors_total"] += 1
    except Exception as e:
        logger.error(f"Fehler beim Tracking eines API-Fehlers: {str(e)}")

def set_health_status(status: str, details: Dict[str, Any] = None):
    """
    Aktualisiert den Health-Status manuell.
    
    Args:
        status: Neuer Status (z.B. "healthy", "degraded", "unhealthy")
        details: Optionale Details zum Status
    """
    global _health_data
    
    try:
        _health_data["status"] = status
        _health_data["last_update"] = time.time()
        
        if details:
            _health_data.update(details)
    except Exception as e:
        logger.error(f"Fehler beim Setzen des Health-Status: {str(e)}")

def get_api_requests_per_minute():
    """
    Berechnet die API-Anfragen pro Minute.
    
    Returns:
        int: Anzahl der API-Anfragen in der letzten Minute
    """
    global _api_request_times
    
    try:
        now = time.time()
        minute_ago = now - 60
        return len([t for t in _api_request_times if t > minute_ago])
    except Exception as e:
        logger.error(f"Fehler bei der Berechnung der API-Anfragen pro Minute: {str(e)}")
        return 0 