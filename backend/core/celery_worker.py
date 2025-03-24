# Am Anfang der Datei - vor allen anderen Importen
try:
    # Patch für billiard/multiprocessing, um mit ungültigen Dateideskriptoren umzugehen
    from billiard.connection import Connection
    
    # Original poll-Methode sichern
    original_poll = Connection._poll
    
    # Patched poll-Methode
    def patched_poll(self, timeout):
        try:
            return original_poll(self, timeout)
        except ValueError as e:
            # Fehler bei ungültigen Dateideskriptoren behandeln
            if "invalid file descriptor" in str(e):
                import logging
                logging.getLogger('billiard_patch').warning(
                    f"Caught invalid file descriptor error in _poll, returning empty list. FD: {getattr(self, 'fileno', lambda: 'unknown')()}"
                )
                return []
            raise
    
    # Die Methode patchen
    Connection._poll = patched_poll
    
    print("Billiard Connection._poll patched successfully in celery_worker.py")
except (ImportError, AttributeError) as e:
    print(f"Could not patch billiard Connection in celery_worker.py: {e}")

# Setze auch Socket-Timeout auf einen höheren Wert
import socket
socket.setdefaulttimeout(120)  # 2 Minuten Timeout

"""
Celery-Worker für HackTheStudy

Dieser Worker verarbeitet Hintergrundaufgaben und längere Berechnungen.
"""

import os
import sys
from celery import Celery
import logging

# Stellen sicher, dass das App-Verzeichnis im Python-Pfad ist
sys.path.insert(0, '/app')

# Konfiguriere Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('celery_worker')

# Importiere Umgebungsvariablen-Handler
try:
    from config.env_handler import load_env
    load_env()
except ImportError:
    logger.warning("Umgebungsvariablen-Handler konnte nicht importiert werden")

# Redis-Verbindungszeichenfolge
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
logger.info(f"Verwende Redis: {redis_url}")

# Erstelle Celery-Instanz
app = Celery('hackthestudy')

# Konfiguration
app.conf.update(
    broker_url=redis_url,
    result_backend=redis_url,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Berlin',
    enable_utc=True,
    task_track_started=True,
    worker_hijack_root_logger=False,
    worker_redirect_stdouts=False,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=7200,  # 2 Stunden Zeitlimit für Tasks
    # Stabilität verbessern, um den ResultHandler-Thread-Absturz zu vermeiden
    worker_send_task_events=False,
    worker_without_heartbeat=True,
    worker_without_gossip=True,
    worker_without_mingle=True,
    worker_enable_remote_control=False,
    # Zusätzliche Resilience-Optionen
    broker_connection_timeout=30,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    result_expires=86400,  # 24 Stunden
    task_ignore_result=False,
    task_store_errors_even_if_ignored=True,
    worker_lost_wait=60.0,  # 1 Minute warten, bevor ein Worker als verloren gilt
    task_send_sent_event=False,
    broker_pool_limit=None,  # Keine Begrenzung für Verbindungen
)

# Importiere Tasks mit korrektem Pfad, da die Datei im Root-Verzeichnis liegt
from tasks import *
app.autodiscover_tasks(['tasks'])

if __name__ == '__main__':
    logger.info("Starting Celery worker")
    app.start() 