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
    try:
        # Versuche zuerst den direkten Import
        import app
        return app.create_app()
    except (ImportError, AttributeError):
        try:
            # Falls das fehlschlägt, versuche den Import mit absoluten Pfaden
            import os
            import sys
            # Füge das übergeordnete Verzeichnis zum Pfad hinzu
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            import app
            return app.create_app()
        except (ImportError, AttributeError):
            # Als letzten Ausweg, versuche die App direkt zu importieren
            try:
                from flask import current_app
                if current_app:
                    return current_app
                
                # Wenn der aktuelle App-Kontext nicht funktioniert, erstelle eine neue App
                from flask import Flask
                flask_app = Flask(__name__)
                # Minimale Konfiguration
                flask_app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
                flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
                # Wir müssen auch die Datenbank initialisieren
                from core.models import db
                db.init_app(flask_app)
                return flask_app
            except Exception as e:
                # Kritischer Fehler - protokolliere Details und verwende eine sehr einfache App als Fallback
                import logging
                logging.critical(f"Kritischer Fehler beim Erstellen der Flask-App: {str(e)}")
                flask_app = Flask(__name__)
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
    Verarbeitet hochgeladene Dateien asynchron mit verbesserter Fehlerbehandlung und Timeout-Management.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"===== WORKER TASK STARTED: {session_id} =====")
    logger.info(f"Worker process PID: {os.getpid()}, Task ID: {self.request.id}")
    logger.info(f"Verarbeite {len(files_data) if files_data else 0} Dateien für Benutzer {user_id or 'anonym'}")
    print(f"DIRECT STDOUT: Worker processing session {session_id}", flush=True)
    start_time = time.time()
    
    # Speichere Task-ID für Tracking
    redis_client.set(f"task_id:{session_id}", self.request.id, ex=14400)  # 4 Stunden Gültigkeit
    
    # Hole die Flask-App und erstelle einen Anwendungskontext
    flask_app = get_flask_app()
    
    # Verwende einen expliziten Anwendungskontext für die gesamte Task
    with flask_app.app_context():
        try:
            # Initialisiere Redis-Status mit detaillierten Informationen
            redis_client.set(f"processing_status:{session_id}", "initializing", ex=14400)
            redis_client.set(f"processing_start_time:{session_id}", str(start_time), ex=14400)
            redis_client.set(f"processing_details:{session_id}", json.dumps({
                "start_time": datetime.now().isoformat(),
                "files_count": len(files_data) if files_data else 0,
                "user_id": user_id,
                "pid": os.getpid(),
                "worker_id": self.request.id,
                "hostname": os.environ.get("HOSTNAME", "unknown"),
                "task_id": self.request.id
            }), ex=14400)
            
            logger.info(f"Session {session_id} - Initializing with {len(files_data) if files_data else 0} files for user {user_id}")
            
            # Wenn keine Dateien übergeben wurden, versuche den Auftrag von Redis wiederherzustellen
            if not files_data or len(files_data) == 0:
                stored_data = redis_client.get(f"upload_files_data:{session_id}")
                if stored_data:
                    files_data = json.loads(stored_data)
                    logger.info(f"Wiederhergestellte Dateidaten aus Redis für Session {session_id}: {len(files_data)} Dateien")
                else:
                    error_msg = f"Keine Dateidaten für Session {session_id} gefunden!"
                    logger.error(error_msg)
                    cleanup_processing_for_session(session_id, "no_files_found")
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
                    upload.processing_status = "processing"
                    upload.updated_at = datetime.now()
                    logger.info(f"💾 Upload-Eintrag gefunden und aktualisiert: ID={upload.id}")
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
            
            # Heartbeat-Mechanismus starten
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
                
                # Hauptverarbeitungslogik
                try:
                    # Aktualisiere den Status
                    redis_client.set(f"processing_status:{session_id}", "extracting_text", ex=14400)
                    
                    # Verarbeite jede Datei
                    results = []
                    for i, file_data in enumerate(files_data):
                        redis_client.set(f"processing_file_index:{session_id}", str(i), ex=14400)
                        redis_client.set(f"processing_file_count:{session_id}", str(len(files_data)), ex=14400)
                        
                        file_name = file_data.get('file_name', f"file_{i}")
                        file_content_b64 = file_data.get('file_content')
                        file_type = file_data.get('mime_type', 'application/octet-stream')
                        
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
                            file_bytes = base64.b64decode(file_content_b64)
                            logger.info(f"📄 Extrahiere Text aus Datei {file_name} ({len(file_bytes)} Bytes)")
                            extracted_text = extract_text_from_file(file_bytes, file_name, file_type)
                            
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
                                total_entries = 0
                                results_summary = []
                                
                                # Zusammenfassen der Ergebnisse
                                if 'flashcards' in file_result:
                                    flashcards_count = len(file_result['flashcards'])
                                    total_entries += flashcards_count
                                    results_summary.append(f"{flashcards_count} Karteikarten")
                                    
                                if 'questions' in file_result:
                                    questions_count = len(file_result['questions'])
                                    total_entries += questions_count
                                    results_summary.append(f"{questions_count} Fragen")
                                    
                                if 'topics' in file_result:
                                    topics_count = len(file_result['topics'])
                                    total_entries += topics_count
                                    results_summary.append(f"{topics_count} Themenbereiche")
                                    
                                if 'main_topic' in file_result and file_result['main_topic']:
                                    results_summary.append(f"Hauptthema: {file_result['main_topic']}")
                                
                                if 'language' in file_result:
                                    results_summary.append(f"Sprache: {file_result['language']}")
                                
                                logger.info(f"✅ Verarbeitung für {file_name} abgeschlossen: {', '.join(results_summary)}")
                            else:
                                logger.warning(f"⚠️ Keine Ergebnisse für Datei {file_name}")
                            logger.info(f"✅ Textverarbeitung für Datei {file_name} abgeschlossen")
                            results.append(file_result)
                            
                        except Exception as file_error:
                            logger.error(f"❌ Fehler bei der Verarbeitung von Datei {file_name}: {str(file_error)}")
                            logger.error(f"❌ Stacktrace: {traceback.format_exc()}")
                            # Füge Fehlerinformationen zum Ergebnis hinzu
                            results.append({
                                "file_name": file_name,
                                "error": str(file_error),
                                "status": "error"
                            })
                    
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
            
            finally:
                # Bereinige den Heartbeat-Thread, wenn er existiert
                if heartbeat_thread and heartbeat_thread.is_alive():
                    logger.info(f"Beende Heartbeat-Thread für Session {session_id}")
                    heartbeat_stop_event.set()  # Signal zum Beenden des Threads
                    # Wir können auf den Thread warten, aber mit Timeout um Blockieren zu vermeiden
                    heartbeat_thread.join(timeout=5.0)
                    # Erzwinge das Ablaufen von Heartbeat-Keys
                    redis_client.delete(f"processing_heartbeat:{session_id}")
        
        except Exception as e:
            # Oberste Fehlerbehandlungsebene - fängt alle nicht abgefangenen Fehler ab
            logger.error(f"Kritischer Fehler bei der Verarbeitung von Session {session_id}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Bereinige alle Ressourcen
            cleanup_processing_for_session(session_id, str(e))
            
            # Erhöhe den Retry-Zähler für diese Task, falls es sich um einen vorübergehenden Fehler handelt
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
        # Bereinige den Text für die Datenbank
        cleaned_text = clean_text_for_database(extracted_text)
        
        # Initialisiere OpenAI-Client
        client = OpenAI()
        
        # Verarbeite den Text mit unified_content_processing
        result = unified_content_processing(
            text=extracted_text,
            client=client,
            file_names=[file_name],
            user_id=user_id,
            session_id=session_id
        )
        
        if not result:
            raise ValueError("Die Inhaltsverarbeitung lieferte ein leeres Ergebnis")
        
        # Speichere die Ergebnisse in der Datenbank
        save_processing_results(session_id, result, user_id)
        
        logger.info(f"Textverarbeitung erfolgreich abgeschlossen für {file_name}")
        
    except Exception as e:
        logger.error(f"Fehler bei der Textverarbeitung: {str(e)}")
        logger.error(traceback.format_exc())
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
            return False
            
        # Speichere die Ergebnisse
        upload.result = result
        upload.status = 'completed'
        upload.completed_at = datetime.utcnow()
        
        # Commit der Änderungen
        db.session.commit()
        
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Ergebnisse: {str(e)}")
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
