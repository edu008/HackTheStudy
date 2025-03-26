"""
Flask-App-Integration für den Worker-Microservice
"""
import os
import logging
import threading
import traceback
from flask import Flask
from celery import Celery

# Logger konfigurieren
logger = logging.getLogger(__name__)

def get_flask_app():
    """
    Erstellt oder gibt die Flask-App zurück.
    Optimiert für die Verwendung im Worker-Kontext.
    
    Returns:
        Eine Flask-App-Instanz
    """
    logger.info("get_flask_app() wird aufgerufen...")
    
    # Einfache, schnelle App-Erstellung mit Timeout
    try:
        # Timeout-Mechanismus mit Thread statt Signal (funktioniert auf allen Plattformen)
        timeout_occurred = [False]
        
        def timeout_function():
            timeout_occurred[0] = True
            logger.warning("Timeout beim Import der Flask-App")
            
        # Setze Timeout von 5 Sekunden für den Import
        timer = threading.Timer(5.0, timeout_function)
        timer.start()
        
        try:
            # Direkter Import ohne Komplikationen
            import app
            if hasattr(app, 'create_app') and not timeout_occurred[0]:
                flask_app = app.create_app()
                logger.info(f"app.create_app() erfolgreich aufgerufen")
                timer.cancel()  # Breche den Timer ab
                return flask_app
        except (ImportError, AttributeError) as e:
            logger.warning(f"Direkter Import fehlgeschlagen: {str(e)}")
        
        # Wenn der direkte Import fehlschlägt, erstelle eine einfache App
        if not timeout_occurred[0]:
            flask_app = Flask(__name__)
            
            # Konfiguriere die Datenbank
            from core.models import init_db
            db = init_db(flask_app)
            
            # Initialisiere Datenbank - hier auf Fehler vorbereitet sein
            try:
                with flask_app.app_context():
                    # Prüfe die Datenbankverbindung
                    from core.models import Upload
                    logger.info("Prüfe Datenbankverbindung mit einer Testabfrage...")
                    test_query = Upload.query.limit(1).all()
                    logger.info(f"Datenbankverbindung erfolgreich hergestellt, {len(test_query)} Ergebnisse gefunden")
            except Exception as db_error:
                logger.error(f"Fehler bei DB-Initialisierung: {str(db_error)}")
                logger.error(f"Stacktrace: {traceback.format_exc()}")
            
            timer.cancel()  # Breche den Timer ab
            logger.info("Einfache Flask-App mit echter Datenbankverbindung erstellt")
            return flask_app
        else:
            # Bei Timeout erstelle eine sehr einfache App ohne Datenbank
            flask_app = Flask(__name__)
            logger.warning("Sehr einfache Fallback-Flask-App erstellt nach Timeout")
            return flask_app
            
    except Exception as e:
        # Bei anderen Fehlern erstelle ebenfalls eine sehr einfache App
        logger.error(f"Fehler beim Erstellen der Flask-App: {str(e)}")
        logger.error(f"Stacktrace: {traceback.format_exc()}")
        flask_app = Flask(__name__)
        logger.warning("Sehr einfache Fallback-Flask-App erstellt nach Fehler")
        return flask_app

def create_celery_app(redis_url=None):
    """
    Erstellt und konfiguriert die Celery-Instanz.
    
    Args:
        redis_url: Optional. Redis-URL für Broker und Backend.
        
    Returns:
        Eine konfigurierte Celery-Instanz
    """
    if not redis_url:
        from config import REDIS_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND
        # Verwende bevorzugt die bereits bereinigte URL aus der config
        broker_url = CELERY_BROKER_URL
        backend_url = CELERY_RESULT_BACKEND
        
        # Log-Ausgabe für Debugging
        logger.info(f"Verwende Redis-URL für Celery: Broker={broker_url}, Backend={backend_url}")
    else:
        # Falls eine URL direkt übergeben wurde
        broker_url = redis_url
        backend_url = redis_url
    
    # Erstelle die Celery-App mit den bereinigten URLs
    celery_app = Celery(
        'backend.worker',
        broker=broker_url,
        backend=backend_url
    )
    
    # Standard-Konfiguration
    celery_app.conf.update(
        worker_pool='solo',  # Verwende den Solo-Pool
        worker_concurrency=1,  # Immer 1 für Solo-Pool
        worker_prefetch_multiplier=1,  # Nur einen Task gleichzeitig für bessere Stabilität
        task_acks_late=True,  # Bestätige Tasks erst nach erfolgreicher Ausführung
        worker_send_task_events=False,  # Deaktiviere Task-Events
        worker_redirect_stdouts=True,  # Leite Stdout/Stderr um
        worker_redirect_stdouts_level='INFO',  # Log-Level für umgeleitete Ausgabe
        broker_connection_timeout=60,  # Verlängerter Timeout für Redis-Verbindung
        broker_connection_retry=True,  # Wiederverbindungen zu Redis erlauben
        broker_connection_max_retries=20,  # Erhöhte Anzahl Wiederverbindungsversuche
        broker_connection_retry_on_startup=True,  # Versuche, beim Start eine Verbindung herzustellen
        broker_pool_limit=None,  # Keine Begrenzung des Pools
        result_expires=3600,  # Ergebnisse nach 1 Stunde löschen
        # Konfiguration für Datei-Deskriptor-Probleme
        worker_without_heartbeat=True,  # Deaktiviere Heartbeat zur Reduzierung von Sockets
        worker_without_gossip=True,  # Deaktiviere Gossip zur Reduzierung von Sockets
        worker_without_mingle=True,  # Deaktiviere Mingle zur Reduzierung von Sockets
        worker_proc_alive_timeout=120.0,  # Erhöhter Timeout für Worker-Prozesse
        task_ignore_result=False,  # Behalte Ergebnisse zur besseren Nachverfolgung
        broker_heartbeat=0,  # Deaktiviere Broker-Heartbeat
        # Verbesserte Fehlertoleranz für Datei-Deskriptor-Probleme
        broker_transport_options={
            'socket_keepalive': False,  # Deaktiviere Socket-Keepalive
            'socket_timeout': 30,       # Erhöhter Socket-Timeout
            'retry_on_timeout': True,   # Wiederhole bei Timeouts
            'max_retries': 5           # Maximale Anzahl an Wiederholungen pro Verbindung
        }
    )
    
    return celery_app

def init_celery(flask_app, celery_instance=None):
    """
    Bindet Celery an den Flask-App-Kontext.
    
    Args:
        flask_app: Die Flask-App-Instanz
        celery_instance: Optional. Die Celery-Instanz, falls bereits erstellt.
        
    Returns:
        Die initialisierte Celery-Instanz
    """
    # Erstelle Celery-Instanz, falls nicht übergeben
    if celery_instance is None:
        celery_instance = create_celery_app()
    
    # Aktualisiere Celery-Config mit der Flask-App-Config
    celery_instance.conf.update(flask_app.config)
    
    class ContextTask(celery_instance.Task):
        abstract = True  # Dies markiert die Klasse als abstrakte Basisklasse für Tasks
        
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)
    
    # Wichtig: Setze ContextTask als Basisklasse für ALLE Tasks
    celery_instance.Task = ContextTask
    
    # Stelle sicher, dass bestehende Tasks aus diesem Modul auch die ContextTask als Basisklasse haben
    for task_name in celery_instance.tasks:
        task = celery_instance.tasks[task_name]
        if task.__module__ == __name__:
            task.__class__ = ContextTask
    
    return celery_instance 