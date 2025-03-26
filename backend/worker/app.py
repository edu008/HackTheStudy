#!/usr/bin/env python
"""
Haupteinstiegspunkt des Worker-Microservices
"""
import os
import sys

# Gevent-Monkey-Patching MUSS vor allen anderen Imports geschehen!
try:
    from gevent import monkey
    # Vollständiges Patching durchführen
    monkey.patch_all(thread=True, socket=True, dns=True, time=True, select=True, 
                    ssl=True, os=True, subprocess=True, sys=False, aggressive=True, 
                    Event=False, builtins=False, signal=True)
    # Erfolg wird später geloggt, nachdem Logging initialisiert wurde
except ImportError:
    # Ignoriere den Fehler hier - er wird später in der Konsole geloggt
    pass

import logging
import time
import threading
import signal
import json

# Initialisiere ein einfaches Basis-Logging für den Start
logging.basicConfig(
    level=logging.INFO,
    format='[WORKER] %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("worker")

# Logge alle Umgebungsvariablen für Debugging-Zwecke
logger.info("=== UMGEBUNGSVARIABLEN FÜR WORKER-PROZESS (DigitalOcean) ===")
redis_vars = {}
digitalocean_vars = {}
app_vars = {}
celery_vars = {}

for key, value in os.environ.items():
    # Maskiere sensible Werte
    masked_value = value
    if any(sensitive in key.lower() for sensitive in ['key', 'secret', 'password', 'token']):
        masked_value = value[:4] + "****" if len(value) > 8 else "****"
    
    # Gruppiere nach Variablentyp
    if key.startswith("REDIS_") or "REDIS" in key:
        redis_vars[key] = masked_value
    elif "DIGITAL_OCEAN" in key or "DO_" in key or "PRIVATE_URL" in key:
        digitalocean_vars[key] = masked_value
    elif key.startswith("CELERY_"):
        celery_vars[key] = masked_value
    else:
        app_vars[key] = masked_value

# Logge die gruppierten Variablen
logger.info(f"REDIS-KONFIGURATION: {json.dumps(redis_vars, indent=2)}")
logger.info(f"DIGITALOCEAN-KONFIGURATION: {json.dumps(digitalocean_vars, indent=2)}")
logger.info(f"CELERY-KONFIGURATION: {json.dumps(celery_vars, indent=2)}")
logger.info(f"APP-KONFIGURATION: (Anzahl Variablen: {len(app_vars)})")
logger.info("=== ENDE UMGEBUNGSVARIABLEN ===")

# Prüfe explizit Redis-Verbindungsdetails
logger.info(f"REDIS_URL: {os.environ.get('REDIS_URL', 'nicht gesetzt')}")
logger.info(f"REDIS_HOST: {os.environ.get('REDIS_HOST', 'nicht gesetzt')}")
logger.info(f"API_HOST: {os.environ.get('API_HOST', 'nicht gesetzt')}")
logger.info(f"API.PRIVATE_URL oder ähnliche: {os.environ.get('api.PRIVATE_URL', os.environ.get('API_PRIVATE_URL', os.environ.get('PRIVATE_URL', 'nicht gesetzt')))}")

# Logge den Status des Monkey-Patching
try:
    if monkey and hasattr(monkey, 'is_module_patched'):
        patched_modules = []
        for module in ['socket', 'ssl', 'os', 'time', 'select', 'thread']:
            if monkey.is_module_patched(module):
                patched_modules.append(module)
        logger.info(f"Gevent-Monkey-Patching erfolgreich angewendet für: {', '.join(patched_modules)}")
    else:
        logger.warning("Gevent-Monkey-Patching wurde nicht durchgeführt!")
except Exception as e:
    logger.warning(f"Konnte Gevent-Monkey-Patching-Status nicht überprüfen: {e}")

# Stelle sicher, dass der Python-Pfad korrekt gesetzt ist
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logger.info(f"Python-Pfad: {sys.path}")

# Stop-Flag für sauberes Herunterfahren
stop_flag = threading.Event()

# Signal-Handler für sauberes Herunterfahren
def handle_exit_signals(signum, frame):
    """Signal-Handler für SIGTERM und SIGINT"""
    logger.info(f"Signal {signum} empfangen, fahre Worker herunter...")
    stop_flag.set()

# Registriere Signal-Handler
signal.signal(signal.SIGINT, handle_exit_signals)
signal.signal(signal.SIGTERM, handle_exit_signals)

# Importiere die Worker-Komponenten
try:
    # Core-Komponenten initialisieren
    try:
        from core.logging import setup_logging
        logger = setup_logging() or logger
    except ImportError:
        logger.warning("Konnte core.logging nicht importieren, verwende Standard-Logger")
    
    # Ressourcen-Manager und Signal-Handler
    try:
        from resource_manager.fd_monitor import check_and_set_fd_limits, monitor_file_descriptors, schedule_periodic_check
        from resource_manager.signals import register_signal_handlers
    except ImportError:
        logger.warning("Konnte resource_manager nicht importieren")
        def check_and_set_fd_limits(): pass
        def monitor_file_descriptors(): pass
        def schedule_periodic_check(): pass
        def register_signal_handlers(): pass
    
    # Health-Check-Server
    try:
        from health.server import start_health_check_server, stop_health_check_server
    except ImportError:
        logger.warning("Konnte health.server nicht importieren")
        def start_health_check_server(): 
            logger.info("Health-Check-Server (Dummy) gestartet")
        def stop_health_check_server(): pass
    
    # Redis-Verbindung initialisieren
    try:
        from redis_utils.client import initialize_redis_connection
    except ImportError:
        logger.warning("Konnte redis_utils.client nicht importieren")
        def initialize_redis_connection(): pass
    
    # Tasks registrieren
    try:
        from tasks import register_tasks
    except ImportError:
        logger.warning("Konnte tasks nicht importieren")
        def register_tasks(app): 
            logger.info("Keine Tasks registriert")
            return {}
    
    # App und Celery initialisieren
    try:
        from core import get_flask_app, create_celery_app, init_celery
    except ImportError:
        logger.warning("Konnte core nicht importieren")
        def get_flask_app(): 
            from flask import Flask
            app = Flask(__name__)
            return app
        def create_celery_app(): 
            from celery import Celery
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
            # Initialisiere Worker-Komponenten
            celery_app, flask_app, registered_tasks = initialize_worker()
            logger.info(f"Registrierte Tasks: {list(registered_tasks.keys()) if registered_tasks else []}")
            
            # Starte Celery-Worker in einem separaten Thread
            def run_celery_worker():
                """Startet einen Celery-Worker im aktuellen Prozess"""
                logger.info("Starte Celery-Worker...")
                argv = [
                    'worker',
                    '--loglevel=INFO',
                    '--concurrency=1',
                    '--without-gossip',
                    '--without-mingle',
                    '--without-heartbeat'
                ]
                try:
                    celery_app.worker_main(argv)
                except Exception as e:
                    logger.error(f"Fehler beim Starten des Celery-Workers: {e}")
            
            # Starte den Celery-Worker
            try:
                logger.info("Worker ist bereit für Tasks")
                
                # Halte den Prozess am Leben und warte auf Shutdown-Signal
                while not stop_flag.is_set():
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Tastaturunterbrechung empfangen")
            finally:
                # Sauberes Herunterfahren
                logger.info("Fahre Worker-Komponenten herunter...")
                # Stoppe Health-Check-Server
                stop_health_check_server()
                logger.info("Health-Check-Server gestoppt")
                logger.info("Worker-Prozess wird beendet")
        
        except KeyboardInterrupt:
            logger.info("Worker-Skript beendet (Keyboard Interrupt)")
        
        except Exception as e:
            logger.error(f"Fehler im Worker-Hauptprozess: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
except ImportError as e:
    logger.error(f"Fehler beim Importieren der Worker-Komponenten: {e}")
    logger.error("Überprüfe, ob alle erforderlichen Module vorhanden sind")
    raise

except Exception as e:
    logger.error(f"Unerwarteter Fehler: {e}")
    import traceback
    logger.error(traceback.format_exc())
    raise 