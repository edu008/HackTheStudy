"""
Haupteinstiegspunkt des Worker-Microservices
"""
import logging
import os
import socket
import time

# Import der Kernmodule
from backend.worker.core import (
    setup_logging,
    log_environment_variables, 
    get_flask_app, 
    create_celery_app, 
    init_celery
)
# Import der Ressourcenmanagement-Module
from backend.worker.ressource_manager import (
    check_and_set_fd_limits, 
    monitor_file_descriptors,
    schedule_periodic_check,
    register_signal_handlers
)
# Import der Health-Check-Module
from backend.worker.health import start_health_check_server
# Import der Redis-Module
from backend.worker.redis import initialize_redis_connection
# Import der Task-Module
from backend.worker.tasks import register_tasks

# Globale Logger-Instanz
logger = None

def initialize_worker():
    """
    Initialisiert den Worker mit allen benötigten Komponenten.
    
    Returns:
        tuple: (celery_app, flask_app, registered_tasks)
    """
    global logger
    
    # 1. Logging einrichten
    logger = setup_logging()
    logger.info("=== WORKER-INITIALISIERUNG GESTARTET ===")
    
    # 2. Umgebungsvariablen protokollieren
    log_environment_variables()
    
    # 3. Datei-Deskriptor-Limits anpassen
    logger.info("Überprüfe und passe Datei-Deskriptor-Limits an")
    check_and_set_fd_limits()
    
    # 4. Redis-Verbindung initialisieren
    logger.info("Initialisiere Redis-Verbindung")
    initialize_redis_connection()
    
    # 5. Signal-Handler registrieren
    logger.info("Registriere Signal-Handler")
    register_signal_handlers()
    
    # 6. Ressourcenüberwachung starten
    logger.info("Starte Ressourcenüberwachung")
    monitor_file_descriptors()
    schedule_periodic_check()
    
    # 7. Health-Check-Server starten
    logger.info("Starte Health-Check-Server")
    start_health_check_server()
    
    # 8. Flask-App erstellen
    logger.info("Erstelle Flask-App")
    flask_app = get_flask_app()
    
    # 9. Celery-App erstellen und an Flask-App binden
    logger.info("Erstelle und initialisiere Celery-App")
    celery_app = create_celery_app()
    celery_app = init_celery(flask_app, celery_app)
    
    # 10. Tasks registrieren
    logger.info("Registriere Celery-Tasks")
    registered_tasks = register_tasks(celery_app)
    
    logger.info("=== WORKER-INITIALISIERUNG ABGESCHLOSSEN ===")
    return celery_app, flask_app, registered_tasks

def start_worker():
    """
    Startet den Celery Worker.
    """
    logger.info("=== WORKER-MODUS AKTIVIERT ===")
    logger.info("Celery Worker wird gestartet...")
    
    # Setze Socket-Timeout für bessere Stabilität
    socket.setdefaulttimeout(120)  # 2 Minuten Timeout
    
    # Optimierte Worker-Konfiguration für Solo-Pool
    worker_concurrency = 1  # Solo-Pool hat immer Concurrency=1
    
    logger.info(f"Worker-Konfiguration: Solo-Pool (keine Concurrency-Einstellung notwendig)")
    
    # Starte den Worker in einem separaten Thread
    import threading
    
    def worker_thread():
        try:
            # Neuere Celery-Methode zum Starten eines Workers
            logger.info("Starte Worker mit Solo-Pool...")
            worker_instance = celery_app.Worker(
                loglevel='INFO',
                traceback=True,
                pool='solo',        # Verwende solo Pool für maximale Stabilität
                task_events=False,
                without_heartbeat=True,  # Deaktiviere Heartbeat für bessere Stabilität
                without_gossip=True,     # Deaktiviere Gossip für bessere Stabilität
                without_mingle=True      # Deaktiviere Mingle für bessere Stabilität
            )
            worker_instance.start()
        except (AttributeError, TypeError) as e:
            logger.warning(f"Konnte Worker nicht mit neuerer Methode starten: {e}")
            # Fallback auf ältere Methode
            logger.info("Fallback auf ältere Worker-Startmethode...")
            from celery.bin import worker
            worker_instance = worker.worker()
            
            # Setze Worker-Optionen
            worker_options = {
                'loglevel': 'INFO',
                'traceback': True,
                'pool': 'solo',
                'task-events': False,
                'app': celery_app,
                'without-heartbeat': True,
                'without-gossip': True,
                'without-mingle': True
            }
            
            # Starte den Worker mit den Optionen
            logger.info(f"Starte Worker mit Solo-Pool")
            worker_instance.run(**worker_options)
    
    # Starte Worker-Thread
    worker_thread = threading.Thread(target=worker_thread, daemon=False)
    worker_thread.start()
    
    logger.info("Worker-Thread wurde gestartet und läuft im Hintergrund")
    return worker_thread

# Haupteinstiegspunkt
if __name__ == "__main__":
    # Initialisiere den Worker
    celery_app, flask_app, registered_tasks = initialize_worker()
    
    # Prüfe Startmodus
    if os.environ.get('RUN_MODE', '').lower() == 'worker':
        # Starte den Worker
        worker_thread = start_worker()
        
        # Warte auf Beendigung des Workers
        worker_thread.join()
    else:
        logger.info("=== KEIN WORKER-MODUS AKTIVIERT ===")
        logger.info("Verwende die RUN_MODE=worker Umgebungsvariable, um den Worker zu starten")
else:
    # Bei Import als Modul: Worker initialisieren
    celery_app, flask_app, registered_tasks = initialize_worker() 