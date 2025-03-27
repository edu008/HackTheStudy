#!/usr/bin/env python
"""
Haupteinstiegspunkt des Worker-Microservices für HackTheStudy
"""
# System-Basis-Imports
import os
import sys

# Gevent-Monkey-Patching MUSS vor allen anderen Imports geschehen!
try:
    from gevent import monkey

    # Vollständiges Patching durchführen
    monkey.patch_all(thread=True, socket=True, dns=True, time=True, select=True,
                     ssl=True, os=True, subprocess=True, sys=False, aggressive=True,
                     Event=False, builtins=False, signal=True)
except ImportError:
    pass

import json
# System und Performance-Imports
import logging
import signal
import threading
import time

# Initialisiere ein einfaches Basis-Logging für den Start
logging.basicConfig(
    level=logging.INFO,
    format='[WORKER] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("worker")

# Stelle sicher, dass der Python-Pfad korrekt gesetzt ist
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logger.info("Python-Pfad: %s", sys.path)

# Zentrale Konfiguration importieren
try:
    from config.config import config

    # Konfiguriere Logging mit der zentralen Konfiguration
    logger = config.setup_logging("worker") or logger
    logger.info("Zentrale Konfiguration geladen")
except ImportError as e:
    logger.warning("Konnte zentrale Konfiguration nicht laden: %s", e)

# Logge Redis-Konfiguration für Debugging-Zwecke
redis_url = os.environ.get('REDIS_URL', config.redis_url if hasattr(config, 'redis_url') else 'nicht gesetzt')
redis_host = os.environ.get('REDIS_HOST', config.redis_host if hasattr(config, 'redis_host') else 'nicht gesetzt')
api_url = os.environ.get('API_URL', config.api_url if hasattr(config, 'api_url') else 'nicht gesetzt')

logger.info("REDIS_URL: %s", redis_url)
logger.info("REDIS_HOST: %s", redis_host)
logger.info("API_URL: %s", api_url)

# Stop-Flag für sauberes Herunterfahren
stop_flag = threading.Event()

# Signal-Handler für sauberes Herunterfahren


def handle_exit_signals(signum, frame):
    """Signal-Handler für SIGTERM und SIGINT"""
    logger.info("Signal %s empfangen, fahre Worker herunter...", signum)
    stop_flag.set()


# Registriere Signal-Handler
signal.signal(signal.SIGINT, handle_exit_signals)
signal.signal(signal.SIGTERM, handle_exit_signals)

# Worker-Komponenten importieren
# Modul-Importe mit Fallback-Funktionalität


def import_module_safely(module_path, fallback_func=None, fallback_msg=None):
    """Importiert ein Modul sicher mit Fallback-Funktionalität"""
    try:
        return __import__(module_path, fromlist=['*'])
    except ImportError:
        if fallback_msg:
            logger.warning(fallback_msg)
        return fallback_func


# Health-Check-Server
health_server = import_module_safely(
    'health.server',
    fallback_func=type('DummyHealthServer', (), {
        'start_health_check_server': lambda: logger.info("Health-Check-Server (Dummy) gestartet") or None,
        'stop_health_check_server': lambda: None
    }),
    fallback_msg="Konnte health.server nicht importieren"
)
start_health_check_server = getattr(health_server, 'start_health_check_server', lambda: None)
stop_health_check_server = getattr(health_server, 'stop_health_check_server', lambda: None)

# Ressourcen-Manager
try:
    from resource_manager.fd_monitor import (check_and_set_fd_limits,
                                             monitor_file_descriptors,
                                             schedule_periodic_check)
except ImportError:
    logger.warning("Konnte resource_manager.fd_monitor nicht importieren")
    def check_and_set_fd_limits(): pass
    def monitor_file_descriptors(): pass
    def schedule_periodic_check(): pass

# Redis und OpenAI-Cache
try:
    from openaicache.cache_manager import initialize_openai_cache
    from redis_utils.client import initialize_redis_connection
except ImportError as e:
    logger.warning("Konnte Redis oder OpenAI-Cache nicht importieren: %s", e)

    def initialize_redis_connection():
        logger.warning("Redis-Verbindung (Dummy) initialisiert")
        return None

    def initialize_openai_cache():
        logger.warning("OpenAI-Cache (Dummy) initialisiert")
        return None

# Task-Registrierung
try:
    from tasks import register_tasks
except ImportError:
    logger.warning("Konnte tasks nicht importieren")

    def register_tasks(app):
        logger.warning("Keine Tasks registriert")
        return {}

# Flask und Celery
try:
    from bootstrap.app_factory import create_app
    from bootstrap.extensions import create_celery_app, init_celery
except ImportError:
    logger.warning("Konnte bootstrap Komponenten nicht importieren")
    from celery import Celery
    from flask import Flask

    def create_app():
        app = Flask(__name__)
        return app

    def create_celery_app():
        app = Celery("worker")
        return app

    def init_celery(flask_app, celery_app):
        return celery_app

# Worker initialisieren


def initialize_worker():
    """
    Initialisiert den Worker mit allen benötigten Komponenten.

    Returns:
        tuple: (celery_app, flask_app, registered_tasks)
    """
    logger.info("=== WORKER-INITIALISIERUNG GESTARTET ===")

    # Datei-Deskriptor-Limits anpassen
    logger.info("Überprüfe und passe Datei-Deskriptor-Limits an")
    check_and_set_fd_limits()

    # Redis-Verbindung initialisieren
    logger.info("Initialisiere Redis-Verbindung")
    redis_client = initialize_redis_connection()

    # OpenAI-Cache initialisieren
    logger.info("Initialisiere OpenAI-Cache")
    openai_cache = initialize_openai_cache()

    # Ressourcenüberwachung starten
    logger.info("Starte Ressourcenüberwachung")
    monitor_file_descriptors()
    schedule_periodic_check()

    # Health-Check-Server starten
    logger.info("Starte Health-Check-Server")
    health_server = start_health_check_server()

    # Flask-App erstellen
    logger.info("Erstelle Flask-App")
    flask_app = create_app()

    # Celery-App erstellen und an Flask-App binden
    logger.info("Erstelle und initialisiere Celery-App")
    celery_app = create_celery_app()
    celery_app = init_celery(flask_app, celery_app)

    # Tasks registrieren
    logger.info("Registriere Celery-Tasks")
    registered_tasks = register_tasks(celery_app)

    logger.info("=== WORKER-INITIALISIERUNG ABGESCHLOSSEN ===")
    return celery_app, flask_app, registered_tasks


# Haupteinstiegspunkt
if __name__ == "__main__":
    # Initialisiere den Worker
    try:
        # Initialisiere Worker-Komponenten
        celery_app, flask_app, registered_tasks = initialize_worker()
        task_keys = list(registered_tasks.keys()) if registered_tasks else []
        logger.info("Registrierte Tasks: %s", task_keys)

        # Starte Celery-Worker in einem separaten Thread
        def run_celery_worker():
            """Startet einen Celery-Worker im aktuellen Prozess"""
            logger.info("Starte Celery-Worker...")

            # Optimierte Celery-Worker-Konfiguration
            concurrency = int(os.environ.get('CELERY_WORKERS', '1'))
            max_tasks_per_child = int(os.environ.get('CELERY_MAX_TASKS_PER_CHILD', '10'))
            pool = os.environ.get('CELERY_POOL', 'solo')

            log_level = os.environ.get("LOG_LEVEL", "INFO")

            argv = [
                'worker',
                f'--loglevel={log_level}',
                f'--concurrency={concurrency}',
                f'--pool={pool}',
                f'--max-tasks-per-child={max_tasks_per_child}'
            ]

            # Zusätzliche Performance-Optimierungen
            if os.environ.get('CELERY_WORKER_WITHOUT_GOSSIP', '1') == '1':
                argv.append('--without-gossip')
            if os.environ.get('CELERY_WORKER_WITHOUT_MINGLE', '1') == '1':
                argv.append('--without-mingle')
            if os.environ.get('CELERY_WORKER_WITHOUT_HEARTBEAT', '1') == '1':
                argv.append('--without-heartbeat')

            try:
                celery_app.worker_main(argv)
            except Exception as e:
                logger.error("Fehler beim Starten des Celery-Workers: %s", e)

        # Starte den Celery-Worker
        try:
            logger.info("Worker ist bereit für Tasks")

            # Starte den Celery-Worker in einem Thread
            logger.info("🚀 Starte Celery-Worker-Thread...")
            worker_thread = threading.Thread(target=run_celery_worker)
            worker_thread.daemon = True
            worker_thread.start()
            logger.info("🌟 Celery-Worker-Thread gestartet")

            # Halte den Prozess am Leben und warte auf Shutdown-Signal
            while not stop_flag.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Tastaturunterbrechung empfangen")
        finally:
            # Sauberes Herunterfahren
            logger.info("Fahre Worker herunter...")
            stop_health_check_server()

            # Leere Log-Handler
            if hasattr(config, 'force_flush_handlers'):
                config.force_flush_handlers()

            logger.info("Worker erfolgreich heruntergefahren")
    except Exception as e:
        logger.critical("Kritischer Fehler beim Initialisieren des Workers: %s", e, exc_info=True)
        sys.exit(1)
