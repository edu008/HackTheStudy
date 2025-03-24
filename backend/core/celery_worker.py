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
Celery-Worker-Hauptmodul für HackTheStudy.

Dieses Modul initialisiert und konfiguriert den Celery-Worker für die
Ausführung von Hintergrundaufgaben und stellt sicher, dass alle notwendigen
Konfigurationen und Umgebungsvariablen geladen werden.
"""

import os
import sys
from celery import Celery
from dotenv import load_dotenv
from core.celeryconfig import configure_celery, CELERY_POOL_TYPE
import logging

# Konfiguriere Logging für den Worker
logger = logging.getLogger('celery_worker')

# Lade Umgebungsvariablen mit verbesserter Fehlerbehandlung
def load_environment():
    """Lädt Umgebungsvariablen mit Fehlerbehandlung"""
    try:
        # Versuche zuerst .env zu laden
        if os.path.exists('.env'):
            load_dotenv(override=True, verbose=True)
            logger.info("Umgebungsvariablen aus .env geladen")
        else:
            logger.warning("Keine .env-Datei gefunden, verwende Systemumgebungsvariablen")
        
        # Überprüfe kritische Umgebungsvariablen
        required_vars = ['REDIS_URL', 'OPENAI_API_KEY']
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        
        if missing_vars:
            logger.error(f"Fehlende kritische Umgebungsvariablen: {', '.join(missing_vars)}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Fehler beim Laden der Umgebungsvariablen: {e}")
        sys.exit(1)

# Initialisiere und konfiguriere Celery
def create_celery_app():
    """
    Erstellt und konfiguriert die Celery-Anwendung für den Worker.
    
    Returns:
        Celery: Die konfigurierte Celery-Anwendung
    """
    # Bereinige Redis-URL
    redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0').strip()
    
    # Erstelle Celery-Anwendung
    app = Celery(
        'tasks',
        broker=redis_url,
        backend=redis_url,
        include=['tasks']  # Importiere Tasks aus tasks.py
    )
    
    # Konfiguriere Celery mit optimierten Einstellungen
    app = configure_celery(app)
    
    # Registriere Signal-Handler für verbesserte Robustheit
    register_signal_handlers(app)
    
    return app

def register_signal_handlers(app):
    """
    Registriert Signal-Handler für Celery-Ereignisse.
    
    Diese Handler verbessern die Robustheit und Fehlerbehandlung des Workers.
    
    Args:
        app: Die Celery-Anwendung
    """
    from celery.signals import (
        worker_ready, worker_init, worker_shutdown,
        task_prerun, task_postrun, task_failure,
        task_retry, task_success, task_revoked
    )
    
    @worker_init.connect
    def worker_init_handler(sender=None, **kwargs):
        logger.info(f"Worker gestartet mit Pool-Typ: {CELERY_POOL_TYPE}")
        
        # Führe Speicherbereinigung durch
        import gc
        gc.collect()
        
        # Melde Speichernutzung für Diagnosezwecke
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            logger.info(f"Initiale Speichernutzung: {memory_info.rss / 1024 / 1024:.2f} MB")
        except ImportError:
            logger.warning("psutil nicht installiert, Speicherüberwachung deaktiviert")
    
    @worker_ready.connect
    def worker_ready_handler(sender=None, **kwargs):
        logger.info("Worker ist bereit und wartet auf Aufgaben")
    
    @worker_shutdown.connect
    def worker_shutdown_handler(sender=None, **kwargs):
        logger.info("Worker wird heruntergefahren, räume Ressourcen auf")
        
        # Führe explizite Ressourcenbereinigung durch
        import gc
        gc.collect()
    
    @task_prerun.connect
    def task_prerun_handler(task_id=None, task=None, **kwargs):
        logger.debug(f"Starte Task: {task.name}[{task_id}]")
    
    @task_postrun.connect
    def task_postrun_handler(task_id=None, task=None, state=None, **kwargs):
        logger.debug(f"Task abgeschlossen: {task.name}[{task_id}] - Status: {state}")
    
    @task_failure.connect
    def task_failure_handler(task_id=None, exception=None, traceback=None, **kwargs):
        logger.error(f"Task fehlgeschlagen: {task_id} - Fehler: {exception}")
    
    @task_success.connect
    def task_success_handler(sender=None, **kwargs):
        logger.debug(f"Task erfolgreich: {sender.request.id}")
    
    @task_retry.connect
    def task_retry_handler(request=None, reason=None, **kwargs):
        logger.warning(f"Task wird wiederholt: {request.id} - Grund: {reason}")

# Hauptinitialisierung
load_environment()
celery = create_celery_app()

if __name__ == '__main__':
    celery.start() 