"""
Thread-Management für das Health-Monitoring-System.
Verwaltet den Monitor-Thread, der in regelmäßigen Abständen den Systemstatus aktualisiert.
"""

import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime

from .base import (get_api_requests_per_minute, get_health_status,
                   set_health_status)
from .connections import (check_celery_connection, check_db_connection,
                          check_redis_connection, store_health_in_redis)
from .resources import (get_cpu_usage, get_memory_usage,
                        get_open_file_descriptors)

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Globale Variablen für Thread-Management
_stop_event = threading.Event()
_monitoring_thread = None


def update_health_data():
    """Aktualisiert die Gesundheitsdaten."""
    try:
        # Speicher- und CPU-Nutzung ermitteln
        memory_bytes, memory_percent = get_memory_usage()
        cpu_percent = get_cpu_usage()

        # Offene Dateien zählen
        open_files = len(get_open_file_descriptors())

        # API-Anfragen pro Minute zählen
        requests_per_minute = get_api_requests_per_minute()

        # Verbindungen überprüfen
        _, db_status = check_db_connection()
        _, redis_status = check_redis_connection()
        _, celery_status = check_celery_connection()

        # Gesamtstatus ermitteln
        status = "healthy"

        # Downgrade auf "degraded", wenn eine Komponente ausgefallen ist
        if "error" in db_status or "error" in redis_status or "error" in celery_status:
            status = "degraded"

        # Health-Daten aktualisieren
        set_health_status(status, {
            "memory_usage_mb": memory_bytes / (1024 * 1024) if memory_bytes else 0,
            "memory_usage_percent": memory_percent,
            "cpu_usage_percent": cpu_percent,
            "open_files": open_files,
            "api_requests_per_minute": requests_per_minute,
            "database_connection_status": db_status,
            "redis_connection_status": redis_status,
            "celery_connection_status": celery_status
        })

        # In Redis speichern für Worker-Zugriff
        health_data = get_health_status()
        store_health_in_redis(health_data)

        return health_data

    except Exception as e:
        logger.error("Fehler bei der Aktualisierung des Health-Status: %s", str(e))
        import traceback
        logger.error(traceback.format_exc())
        return None


def health_monitor_task():
    """Die eigentliche Health-Monitor-Aufgabe, die im Thread ausgeführt wird."""
    logger.info("Health-Monitor-Thread gestartet")

    # Health-Monitoring-Loop
    while not _stop_event.is_set():
        try:
            # Aktualisiere Health-Daten
            health_data = update_health_data()

            # Logge einen Heartbeat alle 5 Minuten
            if int(time.time()) % 300 < 10:
                logger.info("Health-Monitor-Heartbeat: %s", health_data['status'] if health_data else 'unknown')

        except Exception as e:
            logger.error("Fehler im Health-Monitoring: %s", str(e))

        # Alle 30 Sekunden prüfen, mit Möglichkeit zum vorzeitigen Abbruch
        _stop_event.wait(30)

    logger.info("Health-Monitor-Thread wird beendet")


def start_health_monitoring(app=None):
    """
    Startet das Gesundheits-Monitoring.
    Kann in Flask integriert oder als eigenständigen Prozess ausgeführt werden.

    Args:
        app: Optional. Die Flask-Anwendung, falls vorhanden.
    """
    global _monitoring_thread, _stop_event

    logger.info("Health-Monitoring wird initialisiert...")

    # Vorhandene Threads stoppen
    if _monitoring_thread and _monitoring_thread.is_alive():
        logger.info("Vorhandenen Health-Monitor-Thread stoppen...")
        _stop_event.set()
        _monitoring_thread.join(timeout=5)

    # Event zurücksetzen
    _stop_event.clear()

    # Thread starten
    _monitoring_thread = threading.Thread(
        target=health_monitor_task,
        daemon=True,
        name="HealthMonitorThread"
    )
    _monitoring_thread.start()

    logger.info("Health-Monitoring-Thread gestartet")

    # Wenn eine Flask-App übergeben wurde, mit dieser integrieren
    if app:
        from flask import json

        @app.route('/health', methods=['GET'])
        def health_endpoint():
            """Ausführlicher Health-Check-Endpunkt."""
            return json.dumps(get_health_status()), 200, {'Content-Type': 'application/json'}

        @app.route('/simple-health', methods=['GET'])
        def simple_health_endpoint():
            """Einfacher Health-Check-Endpunkt für Load Balancer."""
            health_data = get_health_status()
            if health_data['status'] in ['healthy', 'degraded']:
                return "ok", 200
            return "error", 500

    return _monitoring_thread


def stop_health_monitoring():
    """Stoppt den Health-Monitoring-Thread."""
    global _monitoring_thread, _stop_event

    if _monitoring_thread and _monitoring_thread.is_alive():
        logger.info("Health-Monitor-Thread wird gestoppt...")
        _stop_event.set()
        _monitoring_thread.join(timeout=5)
        logger.info("Health-Monitor-Thread gestoppt")


def run_standalone():
    """Startet das Health-Monitoring als eigenständiges Skript."""
    # Logging konfigurieren
    logging.basicConfig(
        level=logging.INFO,
        format='[HEALTH] %(levelname)s: %(message)s',
        handlers=[logging.StreamHandler()]
    )

    logger.info("Health-Monitor wird als eigenständiges Skript gestartet")

    # Signal-Handler für sauberes Herunterfahren
    def signal_handler(sig, frame):
        logger.info("Signal %s empfangen, fahre herunter...", sig)
        stop_health_monitoring()
        sys.exit(0)

    # Signal-Handler registrieren
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Health-Monitoring starten
    start_health_monitoring()

    # Hauptthread am Leben halten
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard-Interrupt empfangen, beende...")
    finally:
        stop_health_monitoring()
