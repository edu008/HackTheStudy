#!/usr/bin/env python
"""
Haupteinstiegspunkt des Worker-Microservices für HackTheStudy
"""
# System-Basis-Imports
import os
import sys
import uuid

# Gevent-Monkey-Patching MUSS vor allen anderen Imports geschehen!
# try:
#     from gevent import monkey
# 
#     # Vollständiges Patching durchführen (TESTWEISE DEAKTIVIERT)
#     # monkey.patch_all(thread=True, socket=True, dns=True, time=True, select=True,
#     #                  ssl=True, os=True, subprocess=True, sys=False, aggressive=True,
#     #                  Event=False, builtins=False, signal=True)
# except ImportError:
#     pass

import json
# System und Performance-Imports
import logging
import signal
import threading
import time
from datetime import datetime

# Konfiguration importieren
from config.config import config

# Logging einrichten
logger = config.setup_logging("worker")
if not logger:
    # Fallback-Logging einrichten
    logging.basicConfig(
        level=logging.INFO,
        format='[WORKER] %(levelname)s: %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger = logging.getLogger("worker")

# Verbessere die Debug-Informationen
logger.info("Python-Pfad: %s", sys.path)
logger.info(f"REDIS_URL: {config.redis_url}")
logger.info(f"REDIS_HOST: {config.redis_host}")
logger.info(f"REDIS_PORT: {config.redis_port}")
logger.info(f"API_URL: {config.api_url}")

# Teste aktiv die Redis-Verbindung
try:
    import redis
    redis_client = redis.from_url(config.redis_url)
    redis_info = redis_client.info()
    redis_version = redis_info.get('redis_version', 'unbekannt')
    logger.info(f"✅ Redis-Verbindung erfolgreich hergestellt. Version: {redis_version}")
    
    # Teste, ob Redis-Keys gesetzt werden können
    test_key = f"worker:test:{uuid.uuid4()}"
    redis_client.set(test_key, str(datetime.now().isoformat()))
    logger.info(f"✅ Redis-Key '{test_key}' erfolgreich gesetzt")
    
    # Überprüfe vorhandene Queues
    all_keys = redis_client.keys('*')
    queue_keys = [key for key in all_keys if b'queue' in key or b'celery' in key]
    logger.info(f"📋 Vorhandene Redis-Queues: {queue_keys}")
    
except Exception as e:
    logger.error(f"❌ Redis-Verbindungsfehler: {e}")
    logger.exception("Redis-Verbindungsdetails:")

# Flag für sauberes Herunterfahren
stop_event = threading.Event()

# Task-Prozessor-Instanz für die Verarbeitung von Redis-Queue-Nachrichten
task_processor = None

# Signal-Handler für sauberes Herunterfahren
def handle_exit_signals(signum, frame):
    """Signal-Handler für SIGTERM und SIGINT"""
    logger.info("Signal %s empfangen, fahre Worker herunter...", signum)
    # TaskProcessor wird nicht mehr verwendet
    # if task_processor:
    #     task_processor.stop_processing()
    stop_event.set()

# Registriere Signal-Handler
signal.signal(signal.SIGINT, handle_exit_signals)
signal.signal(signal.SIGTERM, handle_exit_signals)

# Worker-Komponenten importieren
try:
    from utils import import_module_safely
    logger.info("Utils-Modul erfolgreich importiert")
except ImportError:
    # Fallback für import_module_safely
    logger.warning("Konnte utils.import_module_safely nicht importieren, verwende lokale Definition")
    
    def import_module_safely(module_paths, fallback=None):
        """Lokale Fallback-Funktion für den Import von Modulen."""
        if not isinstance(module_paths, list):
            module_paths = [module_paths]
            
        for path in module_paths:
            try:
                module = __import__(path, fromlist=['*'])
                logger.info(f"Modul {path} erfolgreich importiert")
                return module
            except ImportError:
                logger.debug(f"Konnte Modul {path} nicht importieren")
        
        logger.warning(f"Konnte keines der Module importieren: {module_paths}")
        return fallback

# Health-Check-Server für Kubernetes-Readiness/Liveness
health_server = import_module_safely(['health.server', 'worker.health.server'])
start_health_check_server = getattr(health_server, 'start_health_check_server', lambda: logger.info("Health-Check-Server (Dummy) gestartet") or None)
stop_health_check_server = getattr(health_server, 'stop_health_check_server', lambda: None)

# Redis-Client und OpenAI-Cache
from redis_utils.client import initialize_redis_connection

# Task-Registrierung und Task-Processor
from tasks import register_tasks

# Celery-App initialisieren
from celery import Celery

# Celery-App erstellen
celery_app = Celery('worker')

# Celery-Konfiguration laden und anpassen
celery_app.conf.update({
    **config.get_celery_config(),
    'broker_connection_retry_on_startup': True
})
logger.info(f"Celery-Konfiguration aktualisiert: {celery_app.conf.humanize()}")

# === NEU: Explizite Task-Entdeckung ===
# Sage Celery, wo es nach Task-Modulen suchen soll (im Paket 'tasks')
# Das stellt sicher, dass Tasks, die mit @celery_app.task dekoriert sind, gefunden werden.
try:
    celery_app.autodiscover_tasks(['tasks'], related_name='tasks')
    # related_name='tasks' ist wichtig, wenn tasks relativ importiert werden innerhalb des packages
    # Alternative, falls 'tasks' nicht als Top-Level erkannt wird:
    # celery_app.autodiscover_tasks(['worker.tasks'], related_name='tasks') 
    logger.info("Celery Task Auto-Discovery für Paket 'tasks' konfiguriert.")
except Exception as auto_err:
    logger.error(f"Fehler bei celery_app.autodiscover_tasks: {auto_err}")
# ======================================

# Heartbeat-Funktion für Lebenszeichen
def start_heartbeat():
    """Startet einen Thread, der regelmäßig ein Lebenszeichen sendet."""
    import threading
    
    def heartbeat():
        while not stop_event.is_set():
            try:
                # Redis-Verbindung herstellen
                import redis
                redis_client = redis.from_url(config.redis_url)
                
                # Heartbeat-Signal senden
                redis_client.set('worker_heartbeat', str(datetime.now().isoformat()))
                logger.debug(f"Heartbeat-Signal gesendet: {datetime.now().isoformat()}")
                
                # Prüfen, ob Tasks in der Queue sind
                keys = redis_client.keys('*task*')
                if keys:
                    for key in keys:
                        if redis_client.type(key) == b'list':
                            count = redis_client.llen(key)
                            if count > 0:
                                logger.info(f"Queue {key} enthält {count} Tasks")
                
                # 10 Sekunden warten
                time.sleep(10)
                
            except Exception as e:
                logger.error(f"Fehler im Heartbeat-Thread: {e}")
                time.sleep(5)  # Kurze Pause bei Fehler
    
    # Thread starten
    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()
    return heartbeat_thread

# Worker-Initialisierung
def initialize_worker():
    """Initialisiert den Worker mit allen benötigten Komponenten."""
    logger.info("========== WORKER-INITIALISIERUNG GESTARTET ==========")
    
    try:
        # Health-Check-Server starten
        start_health_check_server()
        logger.info("Health-Check-Server gestartet")
        
        # Redis-Verbindung initialisieren
        redis_client = initialize_redis_connection()
        if not redis_client:
            logger.warning("Redis-Verbindung konnte nicht initialisiert werden")
        else:
            logger.info("Redis-Verbindung erfolgreich initialisiert")
        
        # Heartbeat-Thread starten
        heartbeat_thread = start_heartbeat()
        logger.info("Heartbeat-Thread gestartet")
        
        # Tasks bei Celery registrieren (DIESER TEIL KÖNNTE JETZT REDUNDANT SEIN, 
        # da autodiscover verwendet wird, aber zur Sicherheit belassen wir ihn vorerst,
        # falls Tasks nicht standardmäßig gefunden werden)
        tasks = register_tasks(celery_app)
        logger.info(f"Von register_tasks zurückgegebene Tasks: {list(tasks.keys())}")
        
        # Speichere die Tasks im Celery-App-Kontext (Kann evtl. auch weg?)
        # celery_app.tasks.update(tasks)
        
        # === Logging zur Überprüfung (bleibt) ===
        logger.info("--- Prüfe registrierte Tasks in celery_app --- ")
        registered_task_names = list(celery_app.tasks.keys())
        logger.info(f"Offiziell in celery_app registrierte Tasks ({len(registered_task_names)}): {registered_task_names}")
        if 'document.process_document' in registered_task_names:
            logger.info("===> Task 'document.process_document' wurde erfolgreich registriert.")
        else:
            logger.error("===> FEHLER: Task 'document.process_document' NICHT registriert!")
        logger.info("----------------------------------------------")
        # === ENDE NEUES LOGGING ===

        logger.info("========== WORKER-INITIALISIERUNG ABGESCHLOSSEN ==========")
        return True
    
    except Exception as e:
        logger.error(f"Fehler bei der Worker-Initialisierung: {e}")
        return False

def run_celery_worker():
    """Startet den Celery-Worker für die Verarbeitung von Tasks."""
    logger.info("========== CELERY-WORKER WIRD GESTARTET ==========")
    
    # Lese den gewünschten Pool aus der Konfiguration oder .env
    # Standard ist 'prefork', wenn nicht anders gesetzt
    worker_pool_type = os.environ.get('CELERY_POOL', 'prefork')
    logger.info(f"Verwende Celery Worker Pool: {worker_pool_type}")

    # Celery worker Kommandozeilenargumente
    argv = [
        'worker',
        '--loglevel=INFO',
        f'--concurrency={config.worker_concurrency}',
        '--without-gossip',
        '--without-mingle',
        f'--pool={worker_pool_type}'
    ]
    
    # Celery worker starten
    celery_app.worker_main(argv)

# Hauptfunktion
if __name__ == "__main__":
    # Worker initialisieren
    if initialize_worker():
        # Celery-Worker starten
        run_celery_worker()
    else:
        logger.error("Worker-Initialisierung fehlgeschlagen, beende Programm")
        sys.exit(1)
