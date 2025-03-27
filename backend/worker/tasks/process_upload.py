"""
Task zur Verarbeitung von hochgeladenen Dateien
"""
import os
import logging
import time
import json
import traceback
import threading
import signal
from datetime import datetime
from celery.exceptions import SoftTimeLimitExceeded
from core import get_flask_app, acquire_session_lock, release_session_lock
from redis_utils.client import redis_client
from redis_utils.utils import safe_redis_set, safe_redis_get, log_debug_info
from utils import log_function_call
from resource_manager import handle_worker_timeout
from api.upload import process_upload_files

# Logger konfigurieren
logger = logging.getLogger(__name__)

def register_task(celery_app):
    """
    Registriert die process_upload Task bei der Celery-App.
    
    Args:
        celery_app: Die Celery-App-Instanz
    """
    @celery_app.task(
        bind=True, 
        name="process_upload",
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
        # Setze Timeout-Handler für detaillierte Diagnose
        task_start_time = time.time()
        
        def on_soft_timeout(signum, frame):
            """Handler für SoftTimeLimit-Signal"""
            execution_time = time.time() - task_start_time
            diagnostics = handle_worker_timeout(
                task_id=self.request.id,
                task_name="process_upload",
                execution_time=execution_time,
                traceback="".join(traceback.format_stack(frame))
            )
            # Setze relevante Fehlermeldung
            error_msg = f"Worker-Timeout nach {execution_time:.1f}s (Limit: 3600s)"
            # Speichere Diagnose in Redis für Frontend-Zugriff
            safe_redis_set(f"error_details:{session_id}", json.dumps({
                "error_type": "worker_timeout",
                "message": error_msg,
                "diagnostics": diagnostics,
                "timestamp": time.time()
            }), ex=14400)
            # Session-Status aktualisieren
            safe_redis_set(f"processing_status:{session_id}", "error", ex=14400)
            # Originales Signal weiterleiten, um Task zu beenden
            raise SoftTimeLimitExceeded(error_msg)
        
        # Registriere Timeout-Handler
        signal.signal(signal.SIGTERM, on_soft_timeout)
        
        # Protokollierung starten
        logger.info(f"🔄 TASK START: process_upload - Session: {session_id}")
        logger.info(f"Worker PID: {os.getpid()}, Task ID: {self.request.id}")
        
        # Speichere Task-ID für Tracking
        safe_redis_set(f"task_id:{session_id}", self.request.id, ex=14400)
        
        # Task-Initialisierung
        start_time = time.time()
        safe_redis_set(f"processing_start_time:{session_id}", str(start_time), ex=14400)
        safe_redis_set(f"processing_details:{session_id}", json.dumps({
            "start_time": datetime.now().isoformat(),
            "files_count": len(files_data) if files_data else 0,
            "user_id": user_id,
            "task_id": self.request.id
        }), ex=14400)
        
        # Wenn keine Dateien übergeben wurden, versuche die Daten aus Redis zu lesen
        if not files_data or len(files_data) == 0:
            logger.info(f"Keine Dateien übergeben, versuche Redis-Wiederherstellung für Session {session_id}")
            stored_data = redis_client.get(f"upload_files_data:{session_id}")
            if stored_data:
                try:
                    files_data = json.loads(stored_data)
                    logger.info(f"Dateidaten aus Redis wiederhergestellt: {len(files_data)} Dateien")
                except json.JSONDecodeError as json_err:
                    logger.error(f"Fehler beim Dekodieren der Redis-Daten: {str(json_err)}")
                    return {
                        "status": "error", 
                        "error": f"Ungültige JSON-Daten in Redis"
                    }
            else:
                error_msg = f"Keine Dateidaten für Session {session_id} gefunden!"
                logger.error(error_msg)
                safe_redis_set(f"processing_status:{session_id}", "failed", ex=14400)
                safe_redis_set(f"error_details:{session_id}", json.dumps({
                    "message": error_msg,
                    "error_type": "no_files_data"
                }), ex=14400)
                return {
                    "status": "error", 
                    "error": "no_files_found"
                }
        
        # Hole die Flask-App und erstelle einen Anwendungskontext
        try:
            logger.info("Erstelle Flask-App-Kontext")
            flask_app = get_flask_app()
            
            with flask_app.app_context():
                # Versuche, einen Lock für diese Session zu erhalten
                if not acquire_session_lock(session_id):
                    error_msg = f"Konnte keinen Lock für Session {session_id} erhalten"
                    logger.error(error_msg)
                    return {"status": "error", "error": "session_locked"}
                
                try:
                    # Rufe die implementierte Verarbeitungsfunktion aus dem API-Modul auf
                    logger.info(f"Starte Verarbeitung mit process_upload_files für Session {session_id}")
                    result = process_upload_files(session_id, files_data, user_id)
                    
                    # Speichere das Ergebnis in Redis
                    if result.get("success", False):
                        safe_redis_set(f"processing_status:{session_id}", "completed", ex=14400)
                        safe_redis_set(f"processing_result:{session_id}", json.dumps(result), ex=86400)  # 24h
                    else:
                        safe_redis_set(f"processing_status:{session_id}", "failed", ex=14400)
                        if "errors" in result and result["errors"]:
                            safe_redis_set(f"error_details:{session_id}", json.dumps({
                                "errors": result["errors"],
                                "timestamp": time.time()
                            }), ex=14400)
                    
                    # Lock freigeben
                    release_session_lock(session_id)
                    
                    # Verarbeitungszeit protokollieren
                    processing_time = time.time() - start_time
                    logger.info(f"Verarbeitung abgeschlossen in {processing_time:.2f}s")
                    
                    return {
                        "status": "completed" if result.get("success", False) else "error",
                        "processing_time": processing_time,
                        "session_id": session_id,
                        "result": result
                    }
                except Exception as processing_error:
                    logger.error(f"Fehler bei der Verarbeitung: {str(processing_error)}")
                    logger.error(traceback.format_exc())
                    
                    # Lock freigeben
                    release_session_lock(session_id)
                    
                    # Fehler in Redis speichern
                    safe_redis_set(f"processing_status:{session_id}", "failed", ex=14400)
                    safe_redis_set(f"error_details:{session_id}", json.dumps({
                        "message": str(processing_error),
                        "error_type": "processing_error",
                        "timestamp": time.time()
                    }), ex=14400)
                    
                    # Wiederholungsversuch, falls noch nicht die maximale Anzahl erreicht
                    retry_count = self.request.retries
                    max_retries = self.max_retries
                    
                    if retry_count < max_retries:
                        logger.warning(f"Versuche Retry {retry_count + 1}/{max_retries}")
                        safe_redis_set(f"processing_status:{session_id}", f"retrying", ex=14400)
                        raise self.retry(exc=processing_error, countdown=120)
                    
                    return {
                        "status": "error",
                        "error": str(processing_error)
                    }
        except Exception as e:
            logger.error(f"Allgemeiner Fehler: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Status aktualisieren
            safe_redis_set(f"processing_status:{session_id}", "failed", ex=14400)
            safe_redis_set(f"error_details:{session_id}", json.dumps({
                "message": str(e),
                "error_type": "general_error",
                "timestamp": time.time()
            }), ex=14400)
            
            return {
                "status": "error",
                "error": str(e)
            }
    
    # Gib die Task-Funktion zurück
    return process_upload 