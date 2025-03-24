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

# Importiere die benötigten Module
from core.models import db, Upload, Flashcard, Question, Topic, UserActivity, Connection
from core.redis_client import redis_client
from api.utils import extract_text_from_file, unified_content_processing, clean_text_for_database
from api.token_tracking import count_tokens
from api.cleanup import cleanup_processing_for_session

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

# Bereinige Redis-URL
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0').strip()

# Initialisiere Celery
celery = Celery(
    'tasks',
    broker=REDIS_URL,
    backend=REDIS_URL
)

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
    
    # Alle versuchten Import-Wege protokollieren
    attempted_imports = []
    
    try:
        # Versuche zuerst den direkten Import
        logger.info("Versuche direkten Import von app")
        import app
        attempted_imports.append("direkter Import: import app")
        
        if hasattr(app, 'create_app'):
            logger.info("app.create_app() gefunden, rufe auf")
            flask_app = app.create_app()
            logger.info(f"app.create_app() erfolgreich aufgerufen, App: {flask_app}")
            return flask_app
        else:
            logger.warning("app wurde importiert, aber create_app nicht gefunden")
            attempted_imports.append("app importiert, aber create_app() fehlt")
    except (ImportError, AttributeError) as e:
        logger.warning(f"Direkter Import fehlgeschlagen: {str(e)}")
        attempted_imports.append(f"Fehler bei direktem Import: {str(e)}")
        
        try:
            # Falls das fehlschlägt, versuche den Import mit absoluten Pfaden
            logger.info("Versuche Import mit angepasstem sys.path")
            import os
            import sys
            
            # Füge das übergeordnete Verzeichnis zum Pfad hinzu
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            
            # Logge die Pfade für besseres Debugging
            logger.info(f"Aktuelles Verzeichnis: {current_dir}")
            logger.info(f"Übergeordnetes Verzeichnis: {parent_dir}")
            
            sys.path.insert(0, current_dir)
            sys.path.insert(0, parent_dir)
            
            logger.info(f"Python-Pfad erweitert: {sys.path[:5]}")
            attempted_imports.append(f"sys.path erweitert mit: {current_dir} und {parent_dir}")
            
            # Versuche erneut den Import
            logger.info("Versuche erneuten Import von app nach Pfadanpassung")
            import app
            
            if hasattr(app, 'create_app'):
                logger.info("app.create_app() gefunden nach Pfadanpassung")
                flask_app = app.create_app()
                logger.info("App erfolgreich erstellt mit app.create_app()")
                return flask_app
            else:
                logger.warning("app wurde importiert nach Pfadanpassung, aber create_app nicht gefunden")
                attempted_imports.append("app importiert nach Pfadanpassung, aber create_app() fehlt")
        except (ImportError, AttributeError) as e:
            logger.warning(f"Import mit angepasstem Pfad fehlgeschlagen: {str(e)}")
            attempted_imports.append(f"Fehler bei Import mit angepasstem Pfad: {str(e)}")
            
            # Als letzten Ausweg, versuche die App direkt zu importieren
            try:
                logger.info("Letzte Option: Versuche Flask-App aus current_app zu bekommen")
                from flask import current_app
                if current_app:
                    logger.info("Aktuelle App aus Flask-Kontext geholt")
                    return current_app
                
                # Wenn der aktuelle App-Kontext nicht funktioniert, erstelle eine neue App
                logger.info("Keine aktuelle App im Kontext, erstelle neue Flask-App")
                from flask import Flask
                flask_app = Flask(__name__)
                
                # Logge die minimale App-Konfiguration
                logger.info("Erstelle minimale Flask-App-Konfiguration")
                
                # Minimale Konfiguration
                database_url = os.getenv('DATABASE_URL')
                logger.info(f"DATABASE_URL vorhanden: {'Ja' if database_url else 'Nein'}")
                
                flask_app.config['SQLALCHEMY_DATABASE_URI'] = database_url
                flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
                
                # Wir müssen auch die Datenbank initialisieren
                logger.info("Initialisiere Datenbank-Verbindung")
                try:
                    from core.models import db
                    db.init_app(flask_app)
                    logger.info("Datenbank erfolgreich initialisiert")
                except Exception as db_error:
                    logger.error(f"Fehler bei DB-Initialisierung: {str(db_error)}")
                
                logger.info("Minimale Flask-App erstellt und konfiguriert")
                return flask_app
            except Exception as e:
                # Kritischer Fehler - protokolliere Details und verwende eine sehr einfache App als Fallback
                error_msg = f"Kritischer Fehler beim Erstellen der Flask-App: {str(e)}"
                logger.critical(error_msg)
                logger.critical(f"Stacktrace: {traceback.format_exc()}")
                logger.critical(f"Versuchte Import-Wege: {attempted_imports}")
                
                # Versuche eine letzte, ganz einfache App zu erstellen
                try:
                    from flask import Flask
                    flask_app = Flask(__name__)
                    logger.warning("Einfache Fallback-Flask-App ohne Konfiguration erstellt")
                    return flask_app
                except Exception as final_error:
                    logger.critical(f"Konnte nicht einmal eine einfache Flask-App erstellen: {str(final_error)}")
                    raise Exception(f"Flask konnte nicht importiert werden: {str(final_error)}")

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
def acquire_session_lock(session_id, timeout=3600):
    """
    Versucht, einen Lock für die angegebene Session zu erhalten.
    Gibt True zurück, wenn ein Lock erhalten wurde, andernfalls False.
    """
    lock_key = f"session_lock:{session_id}"
    
    # Versuche, den Lock zu erwerben (NX = nur setzen, wenn der Key nicht existiert)
    acquired = redis_client.set(lock_key, "1", ex=timeout, nx=True)
    
    if acquired:
        logger.info(f"Acquired lock for session_id: {session_id}")
        
        # Speichere zusätzliche Informationen für Debug-Zwecke
        redis_client.set(f"session_lock_info:{session_id}", json.dumps({
            "pid": os.getpid(),
            "worker_id": os.environ.get("HOSTNAME", "unknown"),
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
            except:
                pass
                
        return False

# Session-Lock freigeben mit verbesserter Fehlerbehandlung
@log_function_call
def release_session_lock(session_id):
    """Gibt den Lock für die angegebene Session frei."""
    lock_key = f"session_lock:{session_id}"
    lock_info_key = f"session_lock_info:{session_id}"
    
    # Lösche Lock und Informationen
    redis_client.delete(lock_key)
    redis_client.delete(lock_info_key)
    
    # Setze explizit den Status frei
    redis_client.set(f"session_lock_status:{session_id}", "released", ex=3600)
    
    logger.info(f"Released lock for session_id: {session_id}")

@celery.task(bind=True, max_retries=5, default_retry_delay=120, soft_time_limit=3600, time_limit=4000)
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
                        logger.info(f"Heartbeat-Thread für Session {session_id} gestartet")
                        while not heartbeat_stop_event.is_set():
                            try:
                                # Aktualisiere den Zeitstempel
                                current_time = str(time.time())
                                redis_client.set(f"processing_heartbeat:{session_id}", current_time, ex=14400)
                                redis_client.set(f"processing_last_update:{session_id}", current_time, ex=14400)
                                
                                # Log alle 5 Minuten einen Heartbeat zur besseren Nachverfolgung
                                if int(float(current_time)) % 300 < 30:  # Etwa alle 5 Minuten
                                    logger.info(f"Heartbeat für Session {session_id} aktiv")
                                    
                                # Kürzeres Sleep-Intervall für schnellere Reaktionszeit auf Stop-Event
                                for _ in range(15):  # 15 x 2 Sekunden = 30 Sekunden
                                    if heartbeat_stop_event.is_set():
                                        break
                                    time.sleep(2)
                            except Exception as hb_error:
                                logger.error(f"Heartbeat-Fehler für Session {session_id}: {str(hb_error)}")
                                # Kurze Pause bei Fehler, dann weiterversuchen
                                time.sleep(5)
                    
                        logger.info(f"Heartbeat-Thread für Session {session_id} beendet")
                    
                    # Starte den Heartbeat in einem separaten Thread
                    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
                    heartbeat_thread.start()
                    logger.info("Heartbeat-Thread gestartet")
                    
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
                                logger.info(f"�� Datenbankstatus erfolgreich aktualisiert für Session {session_id}")
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
                    db.session.commit()
        except Exception as import_error:
            logger.error(f"Fehler beim Importieren der Module für die Bereinigung: {str(import_error)}")
        
        # 2. Alle Redis-Statusinformationen setzen
        processing_status_key = f"processing_status:{session_id}"
        redis_client.set(processing_status_key, f"failed:{error_reason}", ex=3600)
        
        # 3. Sitzungssperre freigeben, falls sie noch nicht freigegeben wurde
        release_session_lock(session_id)
        
        # 4. Optional: Alle laufenden Celery-Tasks für diese Session abbrechen (fortgeschritten)
        # Dies würde eine Verfolgung der Task-IDs in Redis erfordern
        
        logger.info(f"Bereinigung für Session {session_id} abgeschlossen")
    except Exception as e:
        logger.error(f"Fehler bei der Bereinigung der Session {session_id}: {str(e)}")

# Explizite Registrierung der Aufgabe sicherstellen 
celery.tasks.register(process_upload)

@log_function_call
def process_extracted_text(session_id, extracted_text, file_name, user_id=None):
    """Verarbeitet extrahierten Text aus Dateien und generiert Lernmaterialien."""
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"[{session_id}] Beginne Verarbeitung von extrahiertem Text für {file_name}")
        logger.info(f"[{session_id}] Textlänge: {len(extracted_text)} Zeichen")
        
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
            raise
        
        # Verarbeite den Text mit unified_content_processing
        logger.info(f"[{session_id}] Starte unified_content_processing")
        try:
            # Speichere Status für den Frontend-Fortschritt
            redis_client.set(f"processing_progress:{session_id}", json.dumps({
                "progress": 20,
                "stage": "content_processing",
                "message": "KI-Verarbeitung des Textes wird gestartet...",
                "timestamp": datetime.now().isoformat()
            }), ex=14400)
            
            result = unified_content_processing(
                text=extracted_text,
                client=client,
                file_names=[file_name],
                user_id=user_id,
                session_id=session_id
            )
            logger.info(f"[{session_id}] unified_content_processing abgeschlossen")
            
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
            redis_client.set(f"processing_error:{session_id}", json.dumps({
                "error": "content_processing_error",
                "message": str(processing_error),
                "timestamp": datetime.now().isoformat()
            }), ex=14400)
            
            # Aktualisiere auch Redis-Status
            redis_client.set(f"processing_status:{session_id}", f"error:content_processing", ex=14400)
            
            raise
        
        if not result:
            error_msg = "Die Inhaltsverarbeitung lieferte ein leeres Ergebnis"
            logger.error(f"[{session_id}] {error_msg}")
            
            redis_client.set(f"processing_error:{session_id}", json.dumps({
                "error": "empty_result",
                "message": error_msg,
                "timestamp": datetime.now().isoformat()
            }), ex=14400)
            
            raise ValueError(error_msg)
        
        # Speichere die Ergebnisse in der Datenbank
        logger.info(f"[{session_id}] Speichere Ergebnisse in der Datenbank")
        try:
            save_processing_results(session_id, result, user_id)
            logger.info(f"[{session_id}] Ergebnisse erfolgreich gespeichert")
        except Exception as db_error:
            logger.error(f"[{session_id}] Fehler beim Speichern der Ergebnisse: {str(db_error)}")
            logger.error(traceback.format_exc())
            raise
        
        logger.info(f"[{session_id}] Textverarbeitung erfolgreich abgeschlossen für {file_name}")
        return result
        
    except Exception as e:
        logger.error(f"[{session_id}] Fehler bei der Textverarbeitung: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Stell sicher, dass Fehler in Redis gespeichert wird
        try:
            redis_client.set(f"processing_error:{session_id}", json.dumps({
                "error": "text_processing_error",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
                "file": file_name
            }), ex=14400)
        except:
            pass
            
        raise

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
    
    # Logge API-Requests je nach Konfiguration
    log_api_requests = os.environ.get('LOG_API_REQUESTS', 'false').lower() == 'true'
    if log_api_requests:
        api_request_logger.info("API-Anfragen-Protokollierung wurde aktiviert")
    
    # Optimierte Worker-Konfiguration
    worker_concurrency = int(os.environ.get('CELERY_WORKERS', '1'))  # Default auf 1 Worker
    max_tasks_per_child = int(os.environ.get('CELERY_MAX_TASKS_PER_CHILD', '10'))  # Default auf 10
    
    logger.info(f"Worker-Konfiguration: concurrency={worker_concurrency}, max_tasks_per_child={max_tasks_per_child}")
    
    # Starte den Worker in einem separaten Thread
    import threading
    
    def worker_thread():
        try:
            # Neuere Celery-Methode zum Starten eines Workers
            logger.info("Starte Worker mit neuerer Methode...")
            worker_instance = celery.Worker(
                loglevel='INFO',
                traceback=True,
                concurrency=worker_concurrency,
                max_tasks_per_child=max_tasks_per_child,
                task_events=True,
                optimization='fair',
                prefetch_multiplier=1,  # Nur einen Task gleichzeitig für bessere Stabilität
                without_heartbeat=False,  # Aktiviere Heartbeat für bessere Überwachung
                without_gossip=False,     # Aktiviere Gossip für bessere Kommunikation
                without_mingle=False      # Aktiviere Mingle für bessere Task-Verteilung
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
                'concurrency': worker_concurrency,
                'max-tasks-per-child': max_tasks_per_child,
                'task-events': True,
                'app': celery,
                'optimization': 'fair',
                'prefetch-multiplier': 1,
                'without-heartbeat': False,
                'without-gossip': False,
                'without-mingle': False
            }
            
            # Starte den Worker mit den Optionen
            logger.info(f"Starte Worker mit Optionen: {worker_options}")
            worker_instance.run(**worker_options)
    
    # Starte Worker-Thread
    worker_thread = threading.Thread(target=worker_thread, daemon=False)
    worker_thread.start()
    
    logger.info("Worker-Thread wurde gestartet und läuft im Hintergrund")
    return worker_thread

# Worker-Task für API-Anfragenverarbeitung - wird explizit protokolliert
@celery.task(name="process_api_request", bind=True, max_retries=3)
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
def safe_redis_set(key, value, ex=14400):
    """Sichere Methode zum Setzen von Redis-Werten mit Fehlerbehandlung."""
    try:
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        redis_client.set(key, value, ex=ex)
        return True
    except Exception as e:
        logger.error(f"Redis-Fehler beim Setzen von {key}: {str(e)}")
        return False

# Hilfsfunktion für den Debug-Modus
def log_debug_info(session_id, message, **extra_data):
    """Loggt Debug-Informationen sowohl in die Logs als auch nach Redis."""
    logger.debug(f"[{session_id}] {message}")
    
    try:
        # Speichere Debug-Info in Redis
        debug_data = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            **extra_data
        }
        debug_key = f"debug:{session_id}:{int(time.time())}"
        redis_client.set(debug_key, json.dumps(debug_data), ex=3600)  # 1 Stunde Aufbewahrung
        
        # Aktualisiere den Fortschritt
        progress_key = f"processing_progress:{session_id}"
        progress_data = {
            "progress": extra_data.get("progress", 0),
            "stage": extra_data.get("stage", "debug"),
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        redis_client.set(progress_key, json.dumps(progress_data), ex=14400)
    except:
        # Bei Fehlern in der Debug-Funktion nichts tun
        pass
