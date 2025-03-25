#!/usr/bin/env python
"""
Haupteinstiegspunkt des Worker-Microservices
"""
import os
import sys
import logging
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
logger.info(f"Python-Pfad: {sys.path}")

# Importiere die Worker-Komponenten
try:
    # Core-Komponenten initialisieren
    from core.logging import setup_logging
    logger = setup_logging() or logger
    
    # Ressourcen-Manager und Signal-Handler
    from resource_manager.fd_monitor import check_and_set_fd_limits, monitor_file_descriptors, schedule_periodic_check
    from resource_manager.signals import register_signal_handlers
    
    # Health-Check-Server
    from health.server import start_health_check_server
    
    # Redis-Verbindung initialisieren
    from redis_utils.client import initialize_redis_connection
    
    # Tasks registrieren
    from tasks import register_tasks
    
    # App und Celery initialisieren
    from core import get_flask_app, create_celery_app, init_celery
    
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
        initialize_redis_connection()
        
        # Signal-Handler registrieren
        logger.info("Registriere Signal-Handler")
        register_signal_handlers()
        
        # Ressourcenüberwachung starten
        logger.info("Starte Ressourcenüberwachung")
        monitor_file_descriptors()
        schedule_periodic_check()
        
        # Health-Check-Server starten
        logger.info("Starte Health-Check-Server")
        start_health_check_server()
        
        # Flask-App erstellen
        logger.info("Erstelle Flask-App")
        flask_app = get_flask_app()
        
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
            celery_app, flask_app, registered_tasks = initialize_worker()
            logger.info(f"Registrierte Tasks: {list(registered_tasks.keys())}")
            
            # Halte das Haupt-Worker-Skript am Leben, der eigentliche Worker
            # wird durch Supervisor gestartet/verwaltet
            logger.info("Worker-Skript aktiv - drücke Strg+C zum Beenden")
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Worker-Skript beendet (Keyboard Interrupt)")
    
except ImportError as e:
    logger.error(f"Fehler beim Importieren der Worker-Komponenten: {e}")
    logger.error("Überprüfe, ob alle erforderlichen Module vorhanden sind")
    raise

except Exception as e:
    logger.error(f"Unerwarteter Fehler: {e}")
    import traceback
    logger.error(traceback.format_exc())
    raise 