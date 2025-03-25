import os
import sys
from celery import Celery
import logging
import time
import json
import traceback
from flask import Flask, current_app
from openai import OpenAI
from dotenv import load_dotenv
import inspect  # Für Stack-Trace-Informationen
import hashlib  # Für Kürzung langer Texte
from datetime import datetime
import base64
import functools  # Für Decorator-Funktionen
import threading
from threading import Timer
import signal
import gc  # Garbage Collector für manuelles Memory Management
# Importiere die ausgelagerten Ressourcenverwaltungsfunktionen
from core.resource_manager import (
    check_and_set_fd_limits,
    monitor_file_descriptors,
    cleanup_signal_handler
)

# Konstanten für die Anwendung
REDIS_TTL_DEFAULT = 14400  # 4 Stunden Standard-TTL für Redis-Einträge
REDIS_TTL_SHORT = 3600    # 1 Stunde für kurzlebige Einträge

# Importiere die benötigten Module
from core.models import db, Upload, Flashcard, Question, Topic, UserActivity, Connection
from core.redis_client import redis_client

# Direkter Import der benötigten Funktionen, ohne die ganze API zu importieren
# Dadurch vermeiden wir den Import von payment
try:
    from api.utils import extract_text_from_file, unified_content_processing, clean_text_for_database
    from api.token_tracking import count_tokens
    from api.cleanup import cleanup_processing_for_session
except ImportError as e:
    logger.error(f"Fehler beim Importieren der API-Module: {e}")
    logger.error("Versuche alternative Import-Wege...")
    
    # Alternativ: Manuelles Laden der benötigten Module
    import importlib.util
    
    # Hilfsfunktion zum Importieren von Modulen aus Dateipfaden
    def import_module_from_file(module_name, file_path):
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    
    # Versuche, die benötigten Module direkt zu laden
    try:
        utils_module = import_module_from_file("api.utils", "/app/api/utils.py")
        extract_text_from_file = utils_module.extract_text_from_file
        unified_content_processing = utils_module.unified_content_processing
        clean_text_for_database = utils_module.clean_text_for_database
        
        token_tracking_module = import_module_from_file("api.token_tracking", "/app/api/token_tracking.py")
        count_tokens = token_tracking_module.count_tokens
        
        cleanup_module = import_module_from_file("api.cleanup", "/app/api/cleanup.py")
        cleanup_processing_for_session = cleanup_module.cleanup_processing_for_session
        
        logger.info("Alternativ-Import für API-Module war erfolgreich")
    except Exception as alt_import_error:
        logger.critical(f"Kritischer Fehler beim Importieren der API-Module: {alt_import_error}")
        logger.critical("Worker kann ohne diese Module nicht starten!")
        sys.exit(1)

# Umgebungsvariablen für Logging-Konfiguration prüfen
log_level_str = os.environ.get('LOG_LEVEL', 'INFO')
log_prefix = os.environ.get('LOG_PREFIX', '[WORKER] ')

# Log-Level bestimmen
log_level = getattr(logging, log_level_str.upper(), logging.INFO)

# VERBESSERTE LOGGING-KONFIGURATION FÜR DIGITAL OCEAN
# Umfassende Logging-Konfiguration am Anfang der Datei
logging.basicConfig(
    level=log_level,
    # Optimiertes Format für DigitalOcean App Platform Logs - konsistent mit Flask
    format=f'[%(asctime)s] {log_prefix}[%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Explizit stdout verwenden für DigitalOcean
    ],
    force=True  # Überschreibe alle bestehenden Konfigurationen
)

# Worker-Logging aktivieren (Celery-Kernkomponenten)
celery_logger = logging.getLogger('celery')
celery_logger.setLevel(log_level)
celery_logger.info("🚀 Celery-Worker-Logger aktiviert - Sollte in DigitalOcean Runtime-Logs sichtbar sein")

# Worker-Task-Logging aktivieren
task_logger = logging.getLogger('celery.task')
task_logger.setLevel(log_level)
task_logger.info("📋 Celery-Task-Logger aktiviert")

# Hauptlogger für diese Datei
logger = logging.getLogger(__name__)
logger.setLevel(log_level)
logger.info("📝 Worker-Hauptlogger aktiviert")

# API-Request-Logger
api_request_logger = logging.getLogger('api_requests')
log_api_requests = os.environ.get('LOG_API_REQUESTS', 'false').lower() == 'true'
api_request_logger.setLevel(log_level if log_api_requests else logging.WARNING)
api_request_logger.info("🌐 API-Request-Logger aktiviert")

# Decorator zur Funktionsverfolgung
def log_function_call(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        session_id = None
        # Versuche, session_id aus den Argumenten zu extrahieren
        for arg in args:
            if isinstance(arg, str) and len(arg) > 8 and '-' in arg:
                session_id = arg
                break
        
        # Alternativ aus Kwargs extrahieren
        if not session_id and 'session_id' in kwargs:
            session_id = kwargs['session_id']
            
        logger.info(f"🔄 FUNKTION START: {func.__name__}() - Session: {session_id or 'unbekannt'}")
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(f"✅ FUNKTION ENDE: {func.__name__}() - Ausführungszeit: {execution_time:.2f}s - Session: {session_id or 'unbekannt'}")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ FUNKTION FEHLER: {func.__name__}() - Zeit: {execution_time:.2f}s - Fehler: {str(e)} - Session: {session_id or 'unbekannt'}")
            raise
    
    return wrapper

# Lade Umgebungsvariablen mit verbesserten Optionen
load_dotenv(override=True, verbose=True)

# Erhöhe die Datei-Deskriptor-Limits vor der Celery-Initialisierung
logger.info("Überprüfe und passe Datei-Deskriptor-Limits an")
check_and_set_fd_limits()

# Bereinige Redis-URL
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0').strip()
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost').strip()
USE_API_URL = os.getenv('USE_API_URL', '').strip()
API_HOST = os.getenv('API_HOST', '').strip()
REDIS_FALLBACK_URLS = os.getenv('REDIS_FALLBACK_URLS', '').strip()

# Verbindungskorrektur: Überprüfe mehrere mögliche Redis-Hosts
if 'localhost' in REDIS_URL:
    logger.warning(f"Lokale Redis-URL erkannt. Versuche alternative Verbindungen zu finden...")
    
    # Versuche, alternative Hosts zu verwenden (in Reihenfolge der Priorität)
    potential_hosts = []
    
    # 1. Prüfe USE_API_URL (vom DigitalOcean Variable-Templating)
    if USE_API_URL:
        potential_hosts.append(USE_API_URL)
        logger.info(f"Gefunden USE_API_URL: {USE_API_URL}")
    
    # 2. Prüfe API_HOST (direkt konfiguriert)
    if API_HOST:
        potential_hosts.append(API_HOST)
        logger.info(f"Gefunden API_HOST: {API_HOST}")
    
    # 3. Prüfe REDIS_FALLBACK_URLS (kommagetrennte Liste von Hosts)
    if REDIS_FALLBACK_URLS:
        fallback_urls = [url.strip() for url in REDIS_FALLBACK_URLS.split(',')]
        potential_hosts.extend(fallback_urls)
        logger.info(f"Gefunden REDIS_FALLBACK_URLS: {fallback_urls}")
    
    # 4. Standard-Fallbacks hinzufügen
    default_fallbacks = ["api", "hackthestudy-backend-api", "10.0.0.3", "10.0.0.2"]
    for host in default_fallbacks:
        if host not in potential_hosts:
            potential_hosts.append(host)
    
    # Versuche, jeden Host zu verbinden
    import socket
    for host in potential_hosts:
        try:
            logger.info(f"Teste Verbindung zu {host}:6379...")
            # Schneller Test mit Socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            result = s.connect_ex((host, 6379))
            s.close()
            
            if result == 0:
                # Verbindung möglich
                logger.info(f"Erfolgreiche Verbindung zu {host}:6379!")
                REDIS_URL = f"redis://{host}:6379/0"
                REDIS_HOST = host
                os.environ['REDIS_URL'] = REDIS_URL
                os.environ['REDIS_HOST'] = REDIS_HOST
                logger.info(f"Redis-URL korrigiert zu: {REDIS_URL}")
                break
            else:
                logger.warning(f"Verbindung zu {host}:6379 nicht möglich (Code: {result})")
        except Exception as conn_error:
            logger.warning(f"Fehler beim Verbinden zu {host}: {str(conn_error)}")

logger.info(f"Celery verwendet Redis-URL: {REDIS_URL} (Host: {REDIS_HOST})")

# Prüfe, ob die Redis-URL gültig ist
try:
    import redis
    r = redis.from_url(REDIS_URL, socket_timeout=5)
    r.ping()
    logger.info("Redis-Verbindung erfolgreich getestet!")
except Exception as e:
    logger.warning(f"Redis-Verbindungstest fehlgeschlagen: {str(e)}")
    logger.warning("Celery wird trotzdem versuchen, eine Verbindung herzustellen...")

# Überwache Datei-Deskriptoren während der Initialisierung
monitor_file_descriptors()

# Registriere Signal-Handler
signal.signal(signal.SIGTERM, cleanup_signal_handler)
signal.signal(signal.SIGINT, cleanup_signal_handler)

# Initialisiere Celery
celery = Celery(
    'tasks',
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Standard-Konfiguration
celery.conf.update(
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

# Periodische Ressourcenüberwachung einrichten
def periodic_resource_check():
    """Führt regelmäßige Ressourcenüberwachung und -bereinigung durch."""
    try:
        fd_count = monitor_file_descriptors()
        
        # Wenn mehr als 200 Datei-Deskriptoren offen sind, führe zusätzliche Bereinigung durch
        if fd_count > 200:
            logger.warning(f"Kritische Anzahl offener Datei-Deskriptoren: {fd_count}")
            gc.collect()  # Erzwinge Garbage Collection
            
        # Für große Anzahl an Datei-Deskriptoren könnten wir den Worker neustarten
        if fd_count > 500:
            logger.error(f"Zu viele offene Datei-Deskriptoren: {fd_count}. Worker sollte neu gestartet werden.")
            # Dies sendet nur ein Signal, statt den Prozess direkt zu beenden
            os.kill(os.getpid(), signal.SIGTERM)
        
        # Plane nächste Überprüfung
        threading.Timer(300, periodic_resource_check).start()  # Alle 5 Minuten prüfen
    except Exception as e:
        logger.error(f"Fehler bei periodischer Ressourcenüberwachung: {e}")
        # Auch bei Fehlern weiter überprüfen
        threading.Timer(300, periodic_resource_check).start()

# Starte erste Ressourcenüberwachung nach Verzögerung
threading.Timer(60, periodic_resource_check).start()  # Erste Überprüfung nach 1 Minute

# Lade die Konfiguration aus einer separaten Datei
try:
    celery.config_from_object('core.celeryconfig')
    print("Celery configuration loaded from celeryconfig.py")
except ImportError:
    print("celeryconfig.py not found, using default configuration")

# Spezielle Logger für OpenAI API-Anfragen und -Antworten
openai_logger = logging.getLogger('openai_api')
openai_logger.setLevel(logging.DEBUG)
openai_logger.addHandler(logging.StreamHandler(sys.stdout))

# Konfiguriere den Handler, um die Logs auf der Konsole auszugeben
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(name)s: %(message)s')
console_handler.setFormatter(formatter)
openai_logger.addHandler(console_handler)

# Konfiguriere auch den api.openai_client-Logger im Worker-Prozess
api_openai_logger = logging.getLogger('api.openai_client')
api_openai_logger.setLevel(logging.DEBUG)
api_openai_logger.addHandler(console_handler)

# Aktiviere auch den Haupt-OpenAI-Logger
openai_lib_logger = logging.getLogger('openai')
openai_lib_logger.setLevel(logging.DEBUG)
openai_lib_logger.addHandler(console_handler)

# Explizites OpenAI-Debugging aktivieren
os.environ['OPENAI_LOG'] = 'debug'

# Function to create or get the Flask app
def get_flask_app():
    logger.info("get_flask_app() wird aufgerufen...")
    
    # Einfache, schnelle App-Erstellung mit Timeout
    try:
        # Timeout-Mechanismus mit Thread statt Signal (funktioniert auf allen Plattformen)
        timeout_occurred = [False]
        result = [None]
        
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
            from flask import Flask
            flask_app = Flask(__name__)
            
            # Minimale Konfiguration
            database_url = os.getenv('DATABASE_URL')
            flask_app.config['SQLALCHEMY_DATABASE_URI'] = database_url
            flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
            
            # Initialisiere Datenbank
            try:
                from core.models import db
                db.init_app(flask_app)
            except Exception as db_error:
                logger.error(f"Fehler bei DB-Initialisierung: {str(db_error)}")
            
            timer.cancel()  # Breche den Timer ab
            logger.info("Einfache Flask-App erstellt")
            return flask_app
        else:
            # Bei Timeout erstelle eine sehr einfache App ohne Datenbank
            from flask import Flask
            flask_app = Flask(__name__)
            logger.warning("Sehr einfache Fallback-Flask-App erstellt nach Timeout")
            return flask_app
            
    except Exception as e:
        # Bei anderen Fehlern erstelle ebenfalls eine sehr einfache App
        logger.error(f"Fehler beim Erstellen der Flask-App: {str(e)}")
        from flask import Flask
        flask_app = Flask(__name__)
        logger.warning("Sehr einfache Fallback-Flask-App erstellt nach Fehler")
        return flask_app

# Configure Celery to use Flask app context
def init_celery(flask_app):
    celery.conf.update(flask_app.config)
    
    class ContextTask(celery.Task):
        abstract = True  # Dies markiert die Klasse als abstrakte Basisklasse für Tasks
        
        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return self.run(*args, **kwargs)
    
    # Wichtig: Setze ContextTask als Basisklasse für ALLE Tasks
    celery.Task = ContextTask
    
    # Stelle sicher, dass bestehende Tasks aus diesem Modul auch die ContextTask als Basisklasse haben
    for task_name in celery.tasks:
        task = celery.tasks[task_name]
        if task.__module__ == __name__:
            task.__class__ = ContextTask
    
    # Zugriff auf die Task-Registry und registriere process_upload erneut
    if 'process_upload' in globals():
        process_upload.bind(celery)
    
    return celery

# Session-Lock Funktion mit Timeout und verbesserte Fehlerbehandlung
@log_function_call
def acquire_session_lock(session_id, timeout=REDIS_TTL_DEFAULT):
    """
    Versucht, einen Lock für die angegebene Session zu erhalten.
    Gibt True zurück, wenn ein Lock erhalten wurde, andernfalls False.
    
    Args:
        session_id: Die ID der Session, für die ein Lock erworben werden soll
        timeout: Timeout in Sekunden, nach dem der Lock automatisch freigegeben wird
    
    Returns:
        bool: True wenn Lock erworben wurde, sonst False
    """
    lock_key = f"session_lock:{session_id}"
    
    # Erstelle eine eindeutige Lock-ID
    unique_lock_id = f"{os.getpid()}-{datetime.now().timestamp()}-{os.environ.get('HOSTNAME', 'unknown')}"
    
    # Versuche, den Lock zu erwerben (NX = nur setzen, wenn der Key nicht existiert)
    acquired = redis_client.set(lock_key, unique_lock_id, ex=timeout, nx=True)
    
    if acquired:
        logger.info(f"Acquired lock for session_id: {session_id} (ID: {unique_lock_id})")
        
        # Speichere zusätzliche Informationen für Debug-Zwecke
        redis_client.set(f"session_lock_info:{session_id}", json.dumps({
            "pid": os.getpid(),
            "worker_id": os.environ.get("HOSTNAME", "unknown"),
            "lock_id": unique_lock_id,
            "acquired_at": datetime.now().isoformat(),
            "timeout": timeout
        }), ex=timeout)
        
        return True
    else:
        logger.info(f"Session {session_id} is already being processed by another task")
        
        # Lese Debug-Informationen, wenn verfügbar
        lock_info = redis_client.get(f"session_lock_info:{session_id}")
        if lock_info:
            try:
                info = json.loads(lock_info)
                logger.info(f"Lock gehalten von: PID {info.get('pid')}, Worker {info.get('worker_id')}, seit {info.get('acquired_at')}")
            except Exception as e:
                logger.warning(f"Konnte Lock-Info nicht lesen: {str(e)}")
                
        return False

# Session-Lock freigeben mit verbesserter Fehlerbehandlung
@log_function_call
def release_session_lock(session_id):
    """
    Gibt den Lock für die angegebene Session frei.
    
    Args:
        session_id: Die ID der Session, deren Lock freigegeben werden soll
    """
    lock_key = f"session_lock:{session_id}"
    lock_info_key = f"session_lock_info:{session_id}"
    
    try:
        # Prüfe, ob wir den Lock besitzen, bevor wir ihn freigeben
        lock_info = redis_client.get(lock_info_key)
        if lock_info:
            try:
                info = json.loads(lock_info)
                current_pid = os.getpid()
                lock_pid = info.get('pid')
                
                if lock_pid and int(lock_pid) != current_pid:
                    logger.warning(f"Versuch, fremden Lock freizugeben! PID {current_pid} vs Lock-PID {lock_pid}")
                    # Hier könnte man entscheiden, den fremden Lock nicht freizugeben
                    # Wir machen es trotzdem, um potenzielle Deadlocks zu vermeiden
            except Exception as e:
                logger.warning(f"Konnte Lock-Info nicht lesen: {str(e)}")
    except Exception as e:
        logger.error(f"Fehler beim Prüfen des Lock-Besitzers: {str(e)}")
    
    # Lösche Lock und Informationen
    try:
        redis_client.delete(lock_key)
        redis_client.delete(lock_info_key)
        
        # Setze explizit den Status frei
        redis_client.set(f"session_lock_status:{session_id}", "released", ex=REDIS_TTL_SHORT)
        
        logger.info(f"Released lock for session_id: {session_id}")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Freigeben des Locks: {str(e)}")
        return False

@celery.task(
    bind=True, 
    max_retries=5, 
    default_retry_delay=120, 
    soft_time_limit=3600, 
    time_limit=4000,
    acks_late=True,
    reject_on_worker_lost=True
)
@log_function_call
def process_upload(self, session_id, files_data, user_id=None):
    """
    Verarbeitet hochgeladene Dateien.
    
    Args:
        session_id: ID der Upload-Session
        files_data: Liste mit Dateinamen und -inhalten als Tupel
        user_id: ID des Benutzers (optional)
        
    Returns:
        dict: Ergebnis der Verarbeitung
    """
    # Direkte Konsolenausgabe für einfache Diagnose
    logger.info(f"🔄 FUNKTION START: process_upload() - Session: {session_id}")
    logger.info(f"===== WORKER TASK STARTED: {session_id} =====")
    logger.info(f"Worker process PID: {os.getpid()}, Task ID: {self.request.id}")
    if user_id:
        logger.info(f"Verarbeite {len(files_data) if files_data else 0} Dateien für Benutzer {user_id}")
    
    # Zusätzliches Debug-Logging
    print(f"DIRECT STDOUT: Worker processing session {session_id}", flush=True)
    logger.info(f"DIREKT: Worker processing session {session_id} - TASK: {self.request.id}")
    start_time = time.time()
    
    # Debug Logging für files_data
    if files_data:
        logger.info(f"files_data enthält {len(files_data)} Dateien")
        for i, file_data in enumerate(files_data):
            # Sicher überprüfen, ob file_data ein Dict, Tupel oder eine Liste ist
            if isinstance(file_data, dict):
                logger.info(f"Datei {i+1}: Name={file_data.get('file_name', 'Unbekannt')}, Größe={len(file_data.get('file_content', '')[:10])}...")
            elif isinstance(file_data, tuple) and len(file_data) >= 2:
                logger.info(f"Datei {i+1}: Name={file_data[0]}, Größe=ca.{len(file_data[1]) // 2 if len(file_data) > 1 else 0} Bytes")
            elif isinstance(file_data, list) and len(file_data) >= 2:
                # Behandle Listen wie Tupel
                logger.info(f"Datei {i+1}: Name={file_data[0]}, Größe=ca.{len(file_data[1]) // 2 if len(file_data) > 1 else 0} Bytes")
            else:
                logger.info(f"Datei {i+1}: Unbekanntes Format: {type(file_data)}")
                
                # Versuche mehr Informationen über die Struktur zu loggen
                try:
                    if hasattr(file_data, '__len__'):
                        logger.info(f"Länge: {len(file_data)}")
                    if hasattr(file_data, '__getitem__'):
                        for j, item in enumerate(file_data[:3]): # Erste 3 Elemente
                            logger.info(f"Element {j}: Typ={type(item)}")
                except:
                    logger.info("Konnte keine weiteren Informationen über das Datenobjekt sammeln")
    else:
        logger.info("WARNUNG: files_data ist leer oder None!")
    
    # Speichere Task-ID für Tracking
    try:
        safe_redis_set(f"task_id:{session_id}", self.request.id, ex=14400)  # 4 Stunden Gültigkeit
        logger.info(f"Task-ID {self.request.id} in Redis gespeichert für Session {session_id}")
    except Exception as e:
        logger.error(f"FEHLER beim Speichern der Task-ID in Redis: {str(e)}")
    
    # Debugging-Info hinzufügen
    try:
        log_debug_info(session_id, "Worker-Task gestartet", 
                      task_id=self.request.id, 
                      pid=os.getpid(),
                      files_count=len(files_data) if files_data else 0)
        logger.info("Debug-Info in Redis gespeichert")
    except Exception as e:
        logger.error(f"FEHLER beim Speichern der Debug-Info: {str(e)}")
    
    # Hole die Flask-App und erstelle einen Anwendungskontext
    try:
        logger.info("Versuche Flask-App zu bekommen")
        flask_app = get_flask_app()
        logger.info("Flask-App erfolgreich geholt")
    except Exception as e:
        logger.error(f"KRITISCHER FEHLER beim Holen der Flask-App: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "error": f"Flask-App konnte nicht initialisiert werden: {str(e)}"
        }
    
    # Verwende einen expliziten Anwendungskontext für die gesamte Task
    try:
        logger.info("Betrete Flask App-Kontext")
        # Log Flask-App-Informationen für Debugging
        logger.info(f"Flask-App-Typ: {type(flask_app)}")
        logger.info(f"Flask-App-Name: {flask_app.name if hasattr(flask_app, 'name') else 'Kein Name'}")
        logger.info(f"Flask-App hat app_context: {hasattr(flask_app, 'app_context')}")
        logger.info("Versuche, mit flask_app.app_context() zu starten...")
        
        with flask_app.app_context():
            logger.info("Erfolgreich in Flask App-Kontext gelangt")
            try:
                # Initialisiere Redis-Status mit detaillierten Informationen
                logger.info("Initialisiere Redis-Status")
                safe_redis_set(f"processing_status:{session_id}", "initializing", ex=14400)
                safe_redis_set(f"processing_start_time:{session_id}", str(start_time), ex=14400)
                safe_redis_set(f"processing_details:{session_id}", {
                    "start_time": datetime.now().isoformat(),
                    "files_count": len(files_data) if files_data else 0,
                    "user_id": user_id,
                    "pid": os.getpid(),
                    "worker_id": self.request.id,
                    "hostname": os.environ.get("HOSTNAME", "unknown"),
                    "task_id": self.request.id
                }, ex=14400)
                logger.info("Redis-Status erfolgreich initialisiert")
                
                logger.info(f"Session {session_id} - Initializing with {len(files_data) if files_data else 0} files for user {user_id}")
                
                # Wenn keine Dateien übergeben wurden, versuche den Auftrag von Redis wiederherzustellen
                if not files_data or len(files_data) == 0:
                    logger.info("Keine Dateien übergeben, versuche Redis-Wiederherstellung")
                    stored_data = redis_client.get(f"upload_files_data:{session_id}")
                    if stored_data:
                        logger.info(f"Daten aus Redis gefunden: {len(stored_data)} Bytes")
                        try:
                            files_data = json.loads(stored_data)
                            logger.info(f"Wiederhergestellte Dateidaten aus Redis für Session {session_id}: {len(files_data)} Dateien")
                            log_debug_info(session_id, f"Dateidaten aus Redis wiederhergestellt", files_count=len(files_data))
                        except json.JSONDecodeError as json_err:
                            logger.error(f"Fehler beim Dekodieren der Redis-Daten: {str(json_err)}")
                            raise ValueError(f"Ungültige JSON-Daten in Redis: {str(json_err)}")
                    else:
                        error_msg = f"Keine Dateidaten für Session {session_id} gefunden!"
                        logger.error(error_msg)
                        cleanup_processing_for_session(session_id, "no_files_found")
                        safe_redis_set(f"error_details:{session_id}", {
                            "message": error_msg,
                            "error_type": "no_files_data",
                            "timestamp": time.time()
                        }, ex=14400)
                        return {"error": "no_files_found", "message": error_msg}
                
                # Versuche, einen Lock für diese Session zu erhalten
                logger.info(f"🔒 Versuche, Lock für Session {session_id} zu erhalten...")
                if not acquire_session_lock(session_id):
                    error_msg = f"Konnte keinen Lock für Session {session_id} erhalten - eine andere Instanz verarbeitet diese bereits."
                    logger.error(error_msg)
                    return {"error": "session_locked", "message": error_msg}
                
                logger.info(f"🔒 Session {session_id} - Lock acquired successfully")
                
                # Aktualisiere Datenbankstatus auf "processing"
                try:
                    from core.models import Upload
                    
                    logger.info(f"💾 Aktualisiere Datenbankstatus für Session {session_id} auf 'processing'")
                    upload = Upload.query.filter_by(session_id=session_id).first()
                    if upload:
                        logger.info(f"Upload-Eintrag gefunden: ID={upload.id}")
                        upload.processing_status = "processing"
                        upload.started_at = datetime.utcnow()
                        logger.info(f"💾 Upload-Eintrag gefunden und aktualisiert: ID={upload.id}")
                        log_debug_info(session_id, "Datenbankstatus aktualisiert: processing", progress=5, stage="database_update")
                    else:
                        logger.warning(f"⚠️ Kein Upload-Eintrag für Session {session_id} in der Datenbank gefunden")
                    
                    db.session.commit()
                    logger.info(f"💾 Datenbankaktualisierung erfolgreich für Session {session_id}")
                except Exception as db_error:
                    db.session.rollback()
                    logger.error(f"❌ Datenbankfehler: {str(db_error)}")
                    logger.error(f"❌ Stacktrace: {traceback.format_exc()}")
                    
                    # Speichere den Fehler in Redis für das Frontend
                    redis_client.set(f"processing_error:{session_id}", json.dumps({
                        "error": "database_error",
                        "message": str(db_error),
                        "timestamp": datetime.now().isoformat()
                    }), ex=14400)
                    
                    # Gib den Lock frei
                    release_session_lock(session_id)
                    
                    # Wirf die Exception für Celery-Retry
                    raise Exception(f"Fehler beim Aktualisieren des Datenbankstatus: {str(db_error)}")
                
                # Herzschlag-Mechanismus starten
                logger.info("Starte Heartbeat-Mechanismus")
                heartbeat_thread = None
                heartbeat_stop_event = threading.Event()
                try:
                    # Verbesserte Heartbeat-Funktion mit Stop-Event
                    def heartbeat():
                        """Thread-Funktion für Heartbeat"""
                        heartbeat_counter = 0
                        logger.info(f"Heartbeat-Thread für Session {session_id} gestartet")
                        
                        while not heartbeat_stop_event.is_set():
                            try:
                                # Aktualisiere den Zeitstempel
                                current_time = time.time()
                                
                                # Verwende safe_redis_set für verbesserte Fehlerbehandlung
                                safe_redis_set(f"processing_heartbeat:{session_id}", str(current_time), ex=REDIS_TTL_DEFAULT)
                                safe_redis_set(f"processing_last_update:{session_id}", str(current_time), ex=REDIS_TTL_DEFAULT)
                                
                                # Inkrementiere Zähler für Log-Zwecke
                                heartbeat_counter += 1
                                
                                # Log alle 10 Heartbeats (ca. 5 Minuten) zur besseren Nachverfolgung
                                if heartbeat_counter % 10 == 0:
                                    logger.info(f"Heartbeat #{heartbeat_counter} für Session {session_id} aktiv")
                                    
                                    # Speichere auch ausführlichere Informationen
                                    safe_redis_set(f"processing_heartbeat_info:{session_id}", {
                                        "count": heartbeat_counter,
                                        "pid": os.getpid(),
                                        "worker_id": self.request.id,
                                        "timestamp": datetime.now().isoformat()
                                    }, ex=REDIS_TTL_DEFAULT)
                                
                                # Kürzeres Sleep-Intervall für schnellere Reaktionszeit auf Stop-Event
                                # Aufgeteilt in kleinere Intervalle, um schneller auf Stop-Event zu reagieren
                                for i in range(15):  # 15 x 2 Sekunden = 30 Sekunden
                                    if heartbeat_stop_event.is_set():
                                        break
                                    time.sleep(2)
                            except Exception as hb_error:
                                logger.error(f"Heartbeat-Fehler für Session {session_id}: {str(hb_error)}")
                                # Kurze Pause bei Fehler, dann weiterversuchen
                                time.sleep(5)
                    
                        logger.info(f"Heartbeat-Thread für Session {session_id} beendet (nach {heartbeat_counter} Heartbeats)")
                    
                    # Starte den Heartbeat in einem separaten Thread
                    heartbeat_thread = threading.Thread(
                        target=heartbeat, 
                        daemon=True,
                        name=f"Heartbeat-{session_id}"
                    )
                    heartbeat_thread.start()
                    logger.info(f"Heartbeat-Thread gestartet (Thread-ID: {heartbeat_thread.ident})")
                    
                    # Hauptverarbeitungslogik
                    try:
                        logger.info("Beginne Hauptverarbeitungslogik")
                        # Aktualisiere den Status
                        redis_client.set(f"processing_status:{session_id}", "extracting_text", ex=14400)
                        
                        # Verarbeite jede Datei
                        results = []
                        logger.info(f"Beginne Verarbeitung von {len(files_data)} Dateien")
                        for i, file_data in enumerate(files_data):
                            logger.info(f"Verarbeite Datei {i+1}/{len(files_data)}")
                            redis_client.set(f"processing_file_index:{session_id}", str(i), ex=14400)
                            redis_client.set(f"processing_file_count:{session_id}", str(len(files_data)), ex=14400)
                            
                            try:
                                # Prüfen, ob file_data ein Dict oder ein Tupel ist
                                if isinstance(file_data, dict):
                                    file_name = file_data.get('file_name', f"file_{i}")
                                    file_content_b64 = file_data.get('file_content')
                                    file_type = file_data.get('mime_type', 'application/octet-stream')
                                elif isinstance(file_data, tuple) and len(file_data) >= 2:
                                    file_name = file_data[0]
                                    file_content_b64 = file_data[1]
                                    file_type = 'application/octet-stream'  # Standard
                                elif isinstance(file_data, list) and len(file_data) >= 2:
                                    # Behandle Listen wie Tupel
                                    file_name = file_data[0]
                                    file_content_b64 = file_data[1]
                                    file_type = 'application/octet-stream'  # Standard
                                    logger.info(f"Liste als Dateiformat für {file_name} erkannt und verarbeitet")
                                else:
                                    logger.error(f"Unbekanntes Format für file_data: {type(file_data)}")
                                    # Versuche, mehr Informationen zu loggen
                                    if hasattr(file_data, '__dict__'):
                                        logger.error(f"Attribute: {dir(file_data)}")
                                    continue
                                
                                # Protokolliere Fortschritt
                                logger.info(f"Session {session_id} - Processing file {i+1}/{len(files_data)}: {file_name}")
                                
                                # Setze den Status für diese Datei
                                redis_client.set(f"processing_current_file:{session_id}", json.dumps({
                                    "index": i,
                                    "name": file_name,
                                    "type": file_type,
                                    "start_time": time.time()
                                }), ex=14400)
                                
                                try:
                                    # Extrahiere Text aus der Datei
                                    logger.info(f"Dekodiere base64 für {file_name}")
                                    try:
                                        # Logge einen Teil des base64-Strings zur Überprüfung
                                        preview_length = min(100, len(file_content_b64))
                                        logger.info(f"Base64-Vorschau: {file_content_b64[:preview_length]}...")
                                        
                                        file_bytes = base64.b64decode(file_content_b64)
                                        logger.info(f"Base64-Dekodierung erfolgreich, {len(file_bytes)} Bytes erhalten")
                                    except Exception as decode_error:
                                        logger.error(f"Fehler bei der Base64-Dekodierung: {str(decode_error)}")
                                        logger.error(f"Base64-Typ: {type(file_content_b64)}")
                                        raise
                                    
                                    logger.info(f"📄 Extrahiere Text aus Datei {file_name} ({len(file_bytes)} Bytes)")
                                    try:
                                        # Import vor Verwendung
                                        from api.utils import extract_text_from_file
                                        logger.info(f"API Utils-Modul importiert")
                                        
                                        # Extrahiere den Text
                                        extracted_text = extract_text_from_file(file_bytes, file_name, file_type)
                                        logger.info(f"Textextraktion für {file_name} erfolgreich abgeschlossen")
                                    except Exception as extract_error:
                                        logger.error(f"Fehler bei der Textextraktion: {str(extract_error)}")
                                        logger.error(traceback.format_exc())
                                        raise
                                    
                                    # Log für extrahierte Textlänge und erste Zeichen
                                    text_preview = extracted_text[:100] + "..." if len(extracted_text) > 100 else extracted_text
                                    logger.info(f"📄 Extrahierter Text: {len(extracted_text)} Zeichen, Vorschau: {text_preview}")
                                    
                                    # Aktualisiere Verarbeitungsstatus
                                    redis_client.set(f"processing_status:{session_id}", f"processing_file_{i+1}", ex=14400)
                                    
                                    # Verarbeite den extrahierten Text
                                    logger.info(f"🧠 Starte KI-Analyse des Textes für Datei {file_name}")
                                    logger.info(f"📊 Geschätzte Textgröße: ~{len(extracted_text)//4} Tokens")
                                    logger.info(f"🔍 Erkenne Sprache und starte Analyse...")
                                    file_result = process_extracted_text(session_id, extracted_text, file_name, user_id)
                                    
                                    # Log die Ergebnisse der Verarbeitung
                                    if file_result:
                                        logger.info(f"Ergebnisse der Verarbeitung für {file_name} erhalten")
                                        results.append(file_result)
                                    else:
                                        logger.warning(f"⚠️ Keine Ergebnisse für Datei {file_name}")
                                    logger.info(f"✅ Textverarbeitung für Datei {file_name} abgeschlossen")
                                    
                                except Exception as file_error:
                                    logger.error(f"❌ Fehler bei der Verarbeitung von Datei {file_name}: {str(file_error)}")
                                    logger.error(f"❌ Stacktrace: {traceback.format_exc()}")
                                    # Füge Fehlerinformationen zum Ergebnis hinzu
                                    results.append({
                                        "file_name": file_name,
                                        "error": str(file_error),
                                        "status": "error"
                                    })
                            except Exception as file_prep_error:
                                logger.error(f"❌ Fehler bei der Vorbereitung von Datei {i}: {str(file_prep_error)}")
                                logger.error(traceback.format_exc())
                        
                        # Speichere die gesammelten Ergebnisse
                        logger.info(f"💾 Speichere Verarbeitungsergebnisse für Session {session_id}: {len(results)} Dateiergebnisse")
                        save_processing_results(session_id, results, user_id)
                        
                        # Aktualisiere den Status auf abgeschlossen
                        redis_client.set(f"processing_status:{session_id}", "completed", ex=14400)
                        redis_client.set(f"processing_end_time:{session_id}", str(time.time()), ex=14400)
                        logger.info(f"✅ Verarbeitung für Session {session_id} abgeschlossen")
                        
                        # Aktualisiere den Datenbankstatus
                        try:
                            logger.info(f"💾 Aktualisiere Datenbankstatus auf 'completed' für Session {session_id}")
                            upload = Upload.query.filter_by(session_id=session_id).first()
                            if upload:
                                upload.processing_status = "completed"
                                upload.updated_at = datetime.now()
                                upload.completion_time = datetime.now()
                                db.session.commit()
                                logger.info(f"💾 Datenbankstatus erfolgreich aktualisiert für Session {session_id}")
                            else:
                                logger.warning(f"⚠️ Kein Upload-Eintrag zum Aktualisieren gefunden für Session {session_id}")
                        except Exception as db_error:
                            logger.error(f"❌ Fehler beim Aktualisieren des Abschlussstatus: {str(db_error)}")
                            logger.error(f"❌ Stacktrace: {traceback.format_exc()}")
                            db.session.rollback()
                        
                        # Gib den Lock frei
                        release_session_lock(session_id)
                        
                        end_time = time.time()
                        processing_time = end_time - start_time
                        logger.info(f"===== WORKER TASK COMPLETED: {session_id} =====")
                        logger.info(f"Total processing time: {processing_time:.2f} seconds")
                        
                        # Erfolgreiches Ergebnis zurückgeben
                        return {
                            "status": "completed",
                            "session_id": session_id,
                            "processing_time": processing_time,
                            "files_processed": len(files_data)
                        }
                    except Exception as processing_error:
                        # Fehlerbehandlung für die Hauptverarbeitung
                        error_message = str(processing_error)
                        logger.error(f"Kritischer Fehler bei der Verarbeitung von Session {session_id}: {error_message}")
                        logger.error(traceback.format_exc())
                        
                        # Speichere den Fehler für das Frontend
                        redis_client.set(f"processing_error:{session_id}", json.dumps({
                            "error": "processing_error",
                            "message": error_message,
                            "timestamp": datetime.now().isoformat()
                        }), ex=14400)
                        
                        # Aktualisiere den Status auf Fehler
                        redis_client.set(f"processing_status:{session_id}", "error", ex=14400)
                        
                        # Versuche, den Datenbankstatus zu aktualisieren
                        try:
                            upload = Upload.query.filter_by(session_id=session_id).first()
                            if upload:
                                upload.processing_status = "error"
                                upload.updated_at = datetime.now()
                                upload.error_message = error_message[:500]  # Begrenze die Länge
                                db.session.commit()
                        except Exception as db_error:
                            logger.error(f"Fehler beim Aktualisieren des Fehlerstatus: {str(db_error)}")
                            db.session.rollback()
                        
                        # Gib den Lock frei
                        release_session_lock(session_id)
                        
                        # Wirf die Exception erneut, damit Celery sie als Fehler erkennt
                        raise processing_error
                
                except Exception as heartbeat_setup_error:
                    # Fehlerbehandlung für Probleme mit dem Heartbeat-Setup
                    logger.error(f"Fehler beim Einrichten des Heartbeat-Mechanismus: {str(heartbeat_setup_error)}")
                    logger.error(traceback.format_exc())
                    
                    # Stelle sicher, dass der Lock freigegeben wird
                    release_session_lock(session_id)
                    
                    # Setze den Status auf Fehler
                    safe_redis_set(f"processing_status:{session_id}", "error:heartbeat_setup", ex=REDIS_TTL_DEFAULT)
                    safe_redis_set(f"processing_error:{session_id}", {
                        "error": "heartbeat_setup_error",
                        "message": str(heartbeat_setup_error),
                        "timestamp": datetime.now().isoformat()
                    }, ex=REDIS_TTL_DEFAULT)
                    
                    # Wirf die Exception weiter
                    raise heartbeat_setup_error
                
            except Exception as app_context_error:
                # Fehlerbehandlung innerhalb des App-Kontexts
                logger.error(f"Fehler im App-Kontext: {str(app_context_error)}")
                logger.error(traceback.format_exc())
                
                # Bereinige Ressourcen
                cleanup_processing_for_session(session_id, str(app_context_error))
                
                # Erhöhe den Retry-Zähler für diese Task
                retry_count = self.request.retries
                max_retries = self.max_retries
                
                if retry_count < max_retries:
                    logger.warning(f"Versuche Retry {retry_count + 1}/{max_retries} für Session {session_id}")
                    redis_client.set(f"processing_status:{session_id}", f"retrying_{retry_count + 1}", ex=14400)
                    raise self.retry(exc=app_context_error, countdown=120)  # Retry in 2 Minuten
                else:
                    # Maximale Anzahl von Retries erreicht
                    logger.error(f"Maximale Anzahl von Retries erreicht für Session {session_id}")
                    redis_client.set(f"processing_status:{session_id}", "failed", ex=14400)
                    redis_client.set(f"processing_error:{session_id}", json.dumps({
                        "error": "max_retries_exceeded",
                        "message": str(app_context_error),
                        "timestamp": datetime.now().isoformat()
                    }), ex=14400)
                    
                    # Aktualisiere auch die Datenbank
                    try:
                        upload = Upload.query.filter_by(session_id=session_id).first()
                        if upload:
                            upload.processing_status = "failed"
                            upload.updated_at = datetime.now()
                            upload.error_message = f"Max retries exceeded: {str(app_context_error)}"[:500]
                            db.session.commit()
                    except Exception as db_error:
                        logger.error(f"Fehler beim Aktualisieren des Fehlerstatus: {str(db_error)}")
                        try:
                            db.session.rollback()
                        except:
                            pass
                
                # Gib ein Fehlerergebnis zurück
                return {
                    "status": "error",
                    "session_id": session_id,
                    "error": str(app_context_error),
                    "traceback": traceback.format_exc()
                }
    except Exception as e:
        # Fehlerbehandlung innerhalb des App-Kontexts
        logger.error(f"Fehler im App-Kontext: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Bereinige Ressourcen
        cleanup_processing_for_session(session_id, str(e))
        
        # Erhöhe den Retry-Zähler für diese Task
        retry_count = self.request.retries
        max_retries = self.max_retries
        
        if retry_count < max_retries:
            logger.warning(f"Versuche Retry {retry_count + 1}/{max_retries} für Session {session_id}")
            redis_client.set(f"processing_status:{session_id}", f"retrying_{retry_count + 1}", ex=14400)
            raise self.retry(exc=e, countdown=120)  # Retry in 2 Minuten
        else:
            # Maximale Anzahl von Retries erreicht
            logger.error(f"Maximale Anzahl von Retries erreicht für Session {session_id}")
            redis_client.set(f"processing_status:{session_id}", "failed", ex=14400)
            redis_client.set(f"processing_error:{session_id}", json.dumps({
                "error": "max_retries_exceeded",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }), ex=14400)
            
            # Aktualisiere auch die Datenbank
            try:
                upload = Upload.query.filter_by(session_id=session_id).first()
                if upload:
                    upload.processing_status = "failed"
                    upload.updated_at = datetime.now()
                    upload.error_message = f"Max retries exceeded: {str(e)}"[:500]
                    db.session.commit()
            except Exception as db_error:
                logger.error(f"Fehler beim Aktualisieren des Fehlerstatus: {str(db_error)}")
                try:
                    db.session.rollback()
                except:
                    pass
        
        # Gib ein Fehlerergebnis zurück
        return {
            "status": "error",
            "session_id": session_id,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
    finally:
        # Bereinige den Heartbeat-Thread, wenn er existiert
        if heartbeat_thread and heartbeat_thread.is_alive():
            logger.info(f"Beende Heartbeat-Thread für Session {session_id}")
            heartbeat_stop_event.set()  # Signal zum Beenden des Threads
            # Wir können auf den Thread warten, aber mit Timeout um Blockieren zu vermeiden
            heartbeat_thread.join(timeout=5.0)
            # Erzwinge das Ablaufen von Heartbeat-Keys
            redis_client.delete(f"processing_heartbeat:{session_id}")
        logger.info("Heartbeat-Thread beendet oder nicht vorhanden")

def cleanup_processing_for_session(session_id, error_reason="unknown"):
    """
    Bereinigt alle laufenden Prozesse und Ressourcen für eine Session, wenn ein Fehler auftritt.
    Stellt sicher, dass keine "Zombie-Verarbeitungen" weiterlaufen.
    
    Args:
        session_id: Die ID der Session, die bereinigt werden soll
        error_reason: Der Grund für den Abbruch
    """
    if not session_id:
        logger.error("Cleanup aufgerufen ohne Session-ID")
        return
        
    try:
        logger.info(f"Bereinige Session {session_id} wegen: {error_reason}")
        
        # Füge das aktuelle Verzeichnis und das übergeordnete Verzeichnis zum Python-Pfad hinzu
        import os
        import sys
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        sys.path.insert(0, current_dir)
        sys.path.insert(0, parent_dir)
        
        # 1. Importiere notwendige Module und Sicherstellen, dass die Session in der Datenbank als fehlgeschlagen markiert ist
        try:
            from core.models import db, Upload
            app = get_flask_app()  # Verwende die bereits definierte Funktion
            
            with app.app_context():
                upload = Upload.query.filter_by(session_id=session_id).first()
                if upload:
                    upload.processing_status = "failed"
                    upload.error_message = f"Abgebrochen: {error_reason}"[:500]
                    upload.updated_at = datetime.utcnow()
                    db.session.commit()
                    logger.info(f"Datenbankstatus für Session {session_id} auf 'failed' gesetzt")
                else:
                    logger.warning(f"Kein Upload-Eintrag für Session {session_id} gefunden")
        except Exception as import_error:
            logger.error(f"Fehler beim Aktualisieren des Datenbankstatus: {str(import_error)}")
            logger.error(traceback.format_exc())
        
        # 2. Alle Redis-Statusinformationen setzen
        processing_status_key = f"processing_status:{session_id}"
        safe_redis_set(processing_status_key, f"failed:{error_reason}", ex=REDIS_TTL_DEFAULT)
        
        # Fehlerdetails speichern
        safe_redis_set(f"error_details:{session_id}", {
            "message": str(error_reason),
            "error_type": "manual_cleanup",
            "timestamp": time.time(),
            "cleanup_time": datetime.now().isoformat()
        }, ex=REDIS_TTL_DEFAULT)
        
        # 3. Bereinige alle mit der Session verbundenen Redis-Schlüssel
        try:
            # Finde alle Schlüssel mit diesem session_id-Präfix
            pattern = f"*:{session_id}*"
            keys = redis_client.keys(pattern)
            
            if keys:
                logger.info(f"Bereinige {len(keys)} Redis-Schlüssel für Session {session_id}")
                # Setze die Lebensdauer aller Schlüssel auf eine Stunde, damit sie früher ablaufen
                for key in keys:
                    if key != processing_status_key and key != f"error_details:{session_id}":
                        try:
                            # TTL auf eine Stunde setzen, aber nicht löschen
                            redis_client.expire(key, REDIS_TTL_SHORT)
                        except Exception as redis_error:
                            logger.warning(f"Konnte TTL für Schlüssel {key} nicht setzen: {str(redis_error)}")
        except Exception as redis_error:
            logger.error(f"Fehler beim Bereinigen der Redis-Schlüssel: {str(redis_error)}")
        
        # 4. Sitzungssperre freigeben, falls sie noch nicht freigegeben wurde
        release_session_lock(session_id)
        
        logger.info(f"Bereinigung für Session {session_id} abgeschlossen")
    except Exception as e:
        logger.error(f"Fehler bei der Bereinigung der Session {session_id}: {str(e)}")
        logger.error(traceback.format_exc())

# Explizite Registrierung der Aufgabe sicherstellen 
celery.tasks.register(process_upload)

@log_function_call
def process_extracted_text(session_id, extracted_text, file_name, user_id=None):
    """
    Verarbeitet extrahierten Text aus Dateien und generiert Lernmaterialien.
    
    Args:
        session_id: Die ID der Upload-Session
        extracted_text: Der extrahierte Text aus der Datei
        file_name: Name der Originaldatei
        user_id: Optional, die ID des Benutzers
        
    Returns:
        dict: Die Ergebnisse der Verarbeitung oder None bei Fehler
    """
    logger = logging.getLogger(__name__)
    
    if not extracted_text:
        logger.warning(f"[{session_id}] Leerer Text für Datei {file_name}")
        return None
    
    try:
        logger.info(f"[{session_id}] Beginne Verarbeitung von extrahiertem Text für {file_name}")
        logger.info(f"[{session_id}] Textlänge: {len(extracted_text)} Zeichen")
        
        # Setze Fortschrittsstatus
        safe_redis_set(f"processing_progress:{session_id}", {
            "progress": 10,
            "stage": "text_cleaning",
            "message": "Text wird für die Verarbeitung vorbereitet...",
            "timestamp": datetime.now().isoformat()
        })
        
        # Bereinige den Text für die Datenbank
        logger.info(f"[{session_id}] Bereinige Text für die Datenbank")
        cleaned_text = clean_text_for_database(extracted_text)
        logger.info(f"[{session_id}] Text bereinigt: {len(cleaned_text)} Zeichen")
        
        # Initialisiere OpenAI-Client
        logger.info(f"[{session_id}] Initialisiere OpenAI-Client")
        try:
            client = OpenAI()
            logger.info(f"[{session_id}] OpenAI-Client erfolgreich erstellt")
        except Exception as client_error:
            logger.error(f"[{session_id}] Fehler beim Erstellen des OpenAI-Clients: {str(client_error)}")
            logger.error(traceback.format_exc())
            
            # Fehler in Redis speichern
            safe_redis_set(f"processing_error:{session_id}", {
                "error": "openai_client_error",
                "message": str(client_error),
                "timestamp": datetime.now().isoformat()
            })
            
            raise
        
        # Verarbeite den Text mit unified_content_processing
        logger.info(f"[{session_id}] Starte unified_content_processing")
        try:
            # Speichere Status für den Frontend-Fortschritt
            safe_redis_set(f"processing_progress:{session_id}", {
                "progress": 20,
                "stage": "content_processing",
                "message": "KI-Verarbeitung des Textes wird gestartet...",
                "timestamp": datetime.now().isoformat()
            })
            
            # Führe die Verarbeitung durch
            result = unified_content_processing(
                text=cleaned_text,
                client=client,
                file_names=[file_name],
                user_id=user_id,
                session_id=session_id
            )
            logger.info(f"[{session_id}] unified_content_processing abgeschlossen")
            
            # Aktualisiere Fortschritt
            safe_redis_set(f"processing_progress:{session_id}", {
                "progress": 80,
                "stage": "content_processed",
                "message": "KI-Verarbeitung abgeschlossen, speichere Ergebnisse...",
                "timestamp": datetime.now().isoformat()
            })
            
            if result:
                # Log Statistiken
                stats = {}
                if 'flashcards' in result:
                    stats['flashcards'] = len(result['flashcards'])
                if 'questions' in result:
                    stats['questions'] = len(result['questions'])
                if 'topics' in result:
                    stats['topics'] = len(result['topics'])
                if 'key_terms' in result:
                    stats['key_terms'] = len(result['key_terms'])
                
                logger.info(f"[{session_id}] Verarbeitungsergebnis enthält: {json.dumps(stats)}")
            else:
                logger.warning(f"[{session_id}] unified_content_processing lieferte leeres Ergebnis")
                
        except Exception as processing_error:
            logger.error(f"[{session_id}] Fehler in unified_content_processing: {str(processing_error)}")
            logger.error(traceback.format_exc())
            
            # Speichere Fehler für das Frontend
            safe_redis_set(f"processing_error:{session_id}", {
                "error": "content_processing_error",
                "message": str(processing_error),
                "timestamp": datetime.now().isoformat()
            })
            
            # Aktualisiere auch Redis-Status
            safe_redis_set(f"processing_status:{session_id}", f"error:content_processing")
            
            raise
        
        if not result:
            error_msg = "Die Inhaltsverarbeitung lieferte ein leeres Ergebnis"
            logger.error(f"[{session_id}] {error_msg}")
            
            safe_redis_set(f"processing_error:{session_id}", {
                "error": "empty_result",
                "message": error_msg,
                "timestamp": datetime.now().isoformat()
            })
            
            raise ValueError(error_msg)
        
        logger.info(f"[{session_id}] Textverarbeitung erfolgreich abgeschlossen für {file_name}")
        return result
        
    except Exception as e:
        logger.error(f"[{session_id}] Fehler bei der Textverarbeitung: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Stelle sicher, dass Fehler in Redis gespeichert wird
        try:
            safe_redis_set(f"processing_error:{session_id}", {
                "error": "text_processing_error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
                "file": file_name
            })
        except Exception as redis_error:
            logger.error(f"[{session_id}] Konnte Fehler nicht in Redis speichern: {str(redis_error)}")
            
        return None

def save_processing_results(session_id, result, user_id):
    """
    Speichert die Verarbeitungsergebnisse in der Datenbank.
    
    Args:
        session_id (str): Die ID der Session
        result (dict): Die Verarbeitungsergebnisse
        user_id (str): Die ID des Benutzers
        
    Returns:
        bool: True bei Erfolg, False bei Fehler
    """
    try:
        # Finde die Upload-Session
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            logger.error(f"Keine Upload-Session gefunden für Session ID: {session_id}")
            # Aktualisiere auch Redis, um den Fehler zu protokollieren
            error_msg = "Keine Upload-Session in der Datenbank gefunden"
            redis_client.set(f"processing_status:{session_id}", f"error:{error_msg}", ex=14400)
            redis_client.set(f"error_details:{session_id}", json.dumps({
                "message": error_msg,
                "error_type": "database_error",
                "timestamp": time.time()
            }), ex=14400)
            return False
            
        # Debug-Log für Ergebnisse
        logger.info(f"Speichere Ergebnisse für Session {session_id}.")
        logger.debug(f"Ergebnistyp: {type(result)}")
        if isinstance(result, dict):
            logger.debug(f"Ergebnisschlüssel: {', '.join(result.keys())}")
        
        # Speichere die Ergebnisse im Upload-Objekt
        upload.result = result
        upload.processing_status = 'completed'
        upload.completed_at = datetime.utcnow()
        
        # Aktualisiere auch Redis
        redis_client.set(f"processing_status:{session_id}", "completed", ex=14400)
        redis_client.set(f"processing_completed:{session_id}", "true", ex=14400)
        redis_client.set(f"processing_completed_at:{session_id}", str(time.time()), ex=14400)
        
        # Speichere die Ergebnisse auch in Redis (für schnelleren Zugriff)
        try:
            result_json = json.dumps(result)
            redis_client.set(f"processing_result:{session_id}", result_json, ex=14400)
            logger.info(f"Ergebnisse in Redis gespeichert für Session {session_id} (Länge: {len(result_json)})")
        except (TypeError, ValueError) as json_err:
            logger.error(f"Fehler beim Konvertieren der Ergebnisse in JSON: {str(json_err)}")
        
        # Commit der Änderungen
        db.session.commit()
        logger.info(f"Alle Ergebnisse erfolgreich gespeichert für Session {session_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Ergebnisse: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Aktualisiere auch Redis mit dem Fehler
        redis_client.set(f"processing_status:{session_id}", f"error:{str(e)}", ex=14400)
        redis_client.set(f"error_details:{session_id}", json.dumps({
            "message": f"Fehler beim Speichern der Ergebnisse: {str(e)}",
            "error_type": "database_error",
            "timestamp": time.time()
        }), ex=14400)
        
        if 'db' in locals():
            db.session.rollback()
        return False

# Worker-Starter-Funktion
def start_worker():
    """Startet den Celery Worker mit optimalen Einstellungen."""
    logger.info("=== WORKER-MODUS AKTIVIERT ===")
    logger.info("Celery Worker wird gestartet...")
    
    # Setze Socket-Timeout für bessere Stabilität
    import socket
    socket.setdefaulttimeout(120)  # 2 Minuten Timeout
    
    # Logge API-Requests je nach Konfiguration
    log_api_requests = os.environ.get('LOG_API_REQUESTS', 'false').lower() == 'true'
    if log_api_requests:
        api_request_logger.info("API-Anfragen-Protokollierung wurde aktiviert")
    
    # Optimierte Worker-Konfiguration für Solo-Pool
    worker_concurrency = 1  # Solo-Pool hat immer Concurrency=1
    
    logger.info(f"Worker-Konfiguration: Solo-Pool (keine Concurrency-Einstellung notwendig)")
    
    # Starte den Worker in einem separaten Thread
    import threading
    
    def worker_thread():
        try:
            # Neuere Celery-Methode zum Starten eines Workers
            logger.info("Starte Worker mit Solo-Pool...")
            worker_instance = celery.Worker(
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
                'app': celery,
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

# Worker-Task für API-Anfragenverarbeitung - wird explizit protokolliert
@celery.task(
    name="process_api_request", 
    bind=True, 
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True
)
def process_api_request(self, endpoint, method, payload=None, user_id=None):
    """Verarbeitet API-Anfragen asynchron und protokolliert sie."""
    log_api_requests = os.environ.get('LOG_API_REQUESTS', 'false').lower() == 'true'
    
    if log_api_requests:
        # Reduziere die Payload für Logging
        safe_payload = "[REDUZIERTE PAYLOAD]"
        if payload and isinstance(payload, dict):
            # Kopiere und filtere die Payload
            safe_payload = payload.copy()
            for key in ['password', 'token', 'api_key', 'secret']:
                if key in safe_payload:
                    safe_payload[key] = '[REDACTED]'
        
        api_request_logger.info(f"Worker verarbeitet API-Anfrage: {method} {endpoint} - User: {user_id} - Payload: {safe_payload}")
    
    try:
        # Eigentliche Verarbeitung der Anfrage
        start_time = time.time()
        result = process_api_task(endpoint, method, payload, user_id)
        processing_time = time.time() - start_time
        
        if log_api_requests:
            api_request_logger.info(f"Worker hat API-Anfrage verarbeitet: {method} {endpoint} - Zeit: {processing_time:.2f}s")
        
        return result
    except Exception as e:
        # Fehlerbehandlung mit Logging
        error_trace = traceback.format_exc()
        logger.error(f"Fehler bei API-Anfragenverarbeitung: {str(e)}")
        logger.error(error_trace)
        
        # Wiederholungsversuche mit exponentieller Backoff-Zeit
        retry_count = self.request.retries
        max_retries = self.max_retries
        
        if retry_count < max_retries:
            backoff = 2 ** retry_count  # Exponentieller Backoff: 1, 2, 4, 8... Sekunden
            logger.info(f"Wiederhole API-Anfrage {method} {endpoint} in {backoff} Sekunden (Versuch {retry_count+1}/{max_retries+1})")
            raise self.retry(exc=e, countdown=backoff)
        else:
            # Maximale Wiederholungsversuche erreicht
            logger.error(f"Maximale Wiederholungsversuche ({max_retries}) für API-Anfrage {method} {endpoint} erreicht. Gebe auf.")
            raise

# Fehlerbehandlung für Redis-Operationen
def safe_redis_set(key, value, ex=REDIS_TTL_DEFAULT):
    """
    Sichere Methode zum Setzen von Redis-Werten mit Fehlerbehandlung.
    
    Args:
        key: Der Redis-Schlüssel
        value: Der zu speichernde Wert (kann ein Objekt sein)
        ex: Ablaufzeit in Sekunden
        
    Returns:
        bool: True bei Erfolg, False bei Fehler
    """
    if not key:
        logger.error("Leerer Redis-Key übergeben")
        return False
        
    try:
        # Umwandeln von komplexen Typen in JSON
        if isinstance(value, (dict, list, tuple)):
            try:
                value = json.dumps(value)
            except (TypeError, ValueError) as json_err:
                logger.error(f"JSON-Serialisierungsfehler für Key {key}: {str(json_err)}")
                # Versuche eine einfachere String-Repräsentation
                value = str(value)
        
        # None-Werte als leeren String speichern
        if value is None:
            value = ""
            
        # Stelle sicher, dass der Wert ein String ist
        if not isinstance(value, (str, bytes, bytearray, memoryview)):
            value = str(value)
            
        # Setze den Wert mit Timeout
        redis_client.set(key, value, ex=ex)
        return True
    except Exception as e:
        logger.error(f"Redis-Fehler beim Setzen von {key}: {str(e)}")
        logger.error(traceback.format_exc())
        return False

# Ergänzende Funktion zum sicheren Lesen aus Redis
def safe_redis_get(key, default=None):
    """
    Sichere Methode zum Lesen von Redis-Werten mit Fehlerbehandlung.
    
    Args:
        key: Der Redis-Schlüssel
        default: Standardwert, falls der Schlüssel nicht existiert
        
    Returns:
        Der Wert aus Redis oder der Standardwert
    """
    if not key:
        return default
        
    try:
        value = redis_client.get(key)
        if value is None:
            return default
            
        # Versuche JSON zu parsen
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            # Wenn kein JSON, gib den Rohwert zurück
            return value
    except Exception as e:
        logger.error(f"Redis-Fehler beim Lesen von {key}: {str(e)}")
        return default

# Hilfsfunktion für den Debug-Modus
def log_debug_info(session_id, message, **extra_data):
    """
    Loggt Debug-Informationen sowohl in die Logs als auch nach Redis.
    
    Args:
        session_id: Die ID der Session
        message: Die zu loggende Nachricht
        **extra_data: Weitere Key-Value-Paare für die Debug-Info
    """
    if not session_id:
        logger.warning("log_debug_info aufgerufen ohne Session-ID")
        return
        
    # Schreibe zuerst ins Log
    logger.debug(f"[{session_id}] {message}")
    
    try:
        # Prüfe auf bestimmte Parameter und formatiere sie besser
        progress = extra_data.get("progress", 0)
        stage = extra_data.get("stage", "debug")
        
        # Speichere Debug-Info in Redis mit Zeitstempel
        debug_data = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            **extra_data
        }
        
        # Verwende eine eindeutige Timestamp für jeden Debug-Eintrag
        timestamp = int(time.time() * 1000)  # Millisekunden für höhere Genauigkeit
        debug_key = f"debug:{session_id}:{timestamp}"
        
        # Speichere mit einer kürzeren Aufbewahrungszeit (1 Stunde)
        safe_redis_set(debug_key, debug_data, ex=REDIS_TTL_SHORT)
        
        # Halte eine Liste der letzten Debug-Einträge (max. 100)
        try:
            # Füge den neuen Key zur Liste hinzu
            debug_list_key = f"debug_list:{session_id}"
            redis_client.lpush(debug_list_key, debug_key)
            redis_client.ltrim(debug_list_key, 0, 99)  # Behalte nur die letzten 100 Einträge
            redis_client.expire(debug_list_key, REDIS_TTL_DEFAULT)
        except Exception as list_error:
            logger.debug(f"Fehler beim Aktualisieren der Debug-Liste: {str(list_error)}")
        
        # Aktualisiere den Fortschritt
        if progress > 0 or stage != "debug":
            progress_key = f"processing_progress:{session_id}"
            progress_data = {
                "progress": progress,
                "stage": stage,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            safe_redis_set(progress_key, progress_data, ex=REDIS_TTL_DEFAULT)
            
            # Aktualisiere auch den letzten Aktualisierungszeitstempel
            safe_redis_set(f"processing_last_update:{session_id}", str(time.time()), ex=REDIS_TTL_DEFAULT)
    except Exception as e:
        # Bei Fehlern in der Debug-Funktion nur loggen, aber nicht abbrechen
        logger.warning(f"Fehler beim Speichern von Debug-Infos: {str(e)}")

# Timeout-Decorator für Funktionen
def timeout(seconds, error_message="Operation timed out"):
    """
    Decorator, der eine Zeitüberschreitung für Funktionen erzwingt.
    
    Args:
        seconds: Timeout in Sekunden
        error_message: Fehlermeldung bei Timeout
        
    Returns:
        Decorator-Funktion
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = [None]
            error = [None]
            finished = [False]
            
            def target():
                try:
                    result[0] = func(*args, **kwargs)
                    finished[0] = True
                except Exception as e:
                    error[0] = e
            
            thread = threading.Thread(target=target)
            thread.daemon = True  # Thread läuft im Hintergrund
            thread.start()
            thread.join(seconds)
            
            if finished[0]:
                if error[0]:
                    raise error[0]
                return result[0]
            else:
                raise TimeoutError(error_message)
                
        return wrapper
    return decorator

# Verbesserte Ressourcenverwaltung - Überprüfe/erhöhe Datei-Deskriptor-Limits
def check_and_set_fd_limits():
    """Überprüft und setzt das Limit für Datei-Deskriptoren."""
    try:
        # Aktuelle Limits abrufen
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        logger.info(f"Aktuelle Datei-Deskriptor-Limits: soft={soft}, hard={hard}")
        
        # Versuche, das Soft-Limit zu erhöhen
        target_soft = min(hard, 65536)  # Setze auf Hard-Limit oder 65536, was niedriger ist
        if soft < target_soft:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target_soft, hard))
            new_soft, new_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            logger.info(f"Datei-Deskriptor-Limits aktualisiert: soft={new_soft}, hard={new_hard}")
        
        return True
    except Exception as e:
        logger.warning(f"Konnte Datei-Deskriptor-Limits nicht anpassen: {e}")
        return False

# Überwachungsfunktion für Datei-Deskriptoren
def monitor_file_descriptors():
    """Überwacht die Anzahl der offenen Datei-Deskriptoren und gibt Informationen aus"""
    try:
        # Importiere psutil explizit im try-Block
        import psutil
        
        process = psutil.Process(os.getpid())
        fds_count = len(process.open_files())
        memory_info = process.memory_info()
        
        logger.info(f"Aktuelle Anzahl offener Datei-Deskriptoren: {fds_count}")
        logger.info(f"Aktuelle RAM-Nutzung: RSS={memory_info.rss / (1024*1024):.2f} MB, VMS={memory_info.vms / (1024*1024):.2f} MB")
        return fds_count
    except ImportError:
        logger.warning("Fehler bei der Überwachung der Datei-Deskriptoren: psutil-Modul nicht verfügbar")
        return -1
    except Exception as e:
        logger.warning(f"Fehler bei der Überwachung der Datei-Deskriptoren: {str(e)}")
        return -1

# Einfacher HTTP-Server für Health-Checks
import threading
import time
import http.server
import socketserver
from functools import partial

def start_health_check_server():
    """Startet einen einfachen HTTP-Server für Health-Checks"""
    try:
        class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/' or self.path == '/health':
                    # Health-Check-Endpunkt
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    
                    # Überprüfe Redis-Verbindung
                    redis_ok = False
                    try:
                        import redis
                        r = redis.from_url(REDIS_URL, socket_timeout=2)
                        r.ping()
                        redis_ok = True
                    except:
                        pass
                    
                    # Gesundheitsstatus
                    health_info = {
                        "status": "healthy" if redis_ok else "degraded",
                        "redis_connected": redis_ok,
                        "worker_uptime": time.time() - start_time,
                        "timestamp": time.time()
                    }
                    
                    self.wfile.write(json.dumps(health_info).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
            
            def log_message(self, format, *args):
                # Unterdrücke Logging für Health-Check-Anfragen
                pass
        
        # Port für Health-Check-Server
        health_port = int(os.environ.get('HEALTH_PORT', 8080))
        handler = partial(HealthCheckHandler)
        
        logger.info(f"Starte Health-Check-Server auf Port {health_port}")
        httpd = socketserver.TCPServer(("", health_port), handler)
        
        # Starte den Server in einem separaten Thread
        server_thread = threading.Thread(target=httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        logger.info(f"Health-Check-Server läuft auf Port {health_port}")
        
    except Exception as e:
        logger.warning(f"Konnte Health-Check-Server nicht starten: {str(e)}")

# Aufzeichnung der Startzeit für Uptime-Berechnung
start_time = time.time()

# Starte HTTP-Server für Health-Checks in einem separaten Thread
start_health_check_server()

# Lade Celery-Konfiguration aus externer Datei, falls vorhanden
try:
    celery.config_from_object('core.celeryconfig')
    print("Celery configuration loaded from celeryconfig.py")
except ImportError:
    print("celeryconfig.py not found, using default configuration")
