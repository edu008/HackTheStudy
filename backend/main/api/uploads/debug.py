"""
Debug-Funktionen für Upload-Prozess.
Bietet erweiterte Debugging-Möglichkeiten für Uploads.
"""

import logging
import json
from datetime import datetime

from flask import jsonify
from core.models import Upload, ProcessingTask, Topic, Flashcard, Question, db
from core.redis_client import get_redis_client

# Logger konfigurieren
logger = logging.getLogger(__name__)

def get_upload_debug_info(session_id):
    """
    Gibt detaillierte Debug-Informationen zu einem Upload zurück.
    
    Args:
        session_id: ID der Upload-Session
        
    Returns:
        JSON mit detaillierten Debug-Informationen
    """
    try:
        # Redis-Client holen
        redis_client = get_redis_client()
        
        # Daten aus verschiedenen Quellen sammeln
        debug_info = {
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "db_data": {},
            "redis_data": {},
            "counts": {},
            "status": {}
        }
        
        # Upload aus der Datenbank holen
        upload = Upload.query.filter_by(session_id=session_id).first()
        
        if not upload:
            logger.warning(f"Kein Upload gefunden für Session ID: {session_id}")
            debug_info["status"]["upload_exists"] = False
            return jsonify(debug_info), 200
        
        # Upload-Daten
        debug_info["db_data"]["upload"] = {
            "id": upload.id,
            "session_id": upload.session_id,
            "processing_status": upload.processing_status,
            "filename": upload.file_name_1 if hasattr(upload, "file_name_1") else None,
            "created_at": upload.created_at.isoformat() if hasattr(upload, "created_at") else None,
            "updated_at": upload.updated_at.isoformat() if hasattr(upload, "updated_at") else None,
            "token_count": upload.token_count if hasattr(upload, "token_count") else None,
        }
        
        # Status-Informationen
        debug_info["status"]["upload_exists"] = True
        debug_info["status"]["upload_processing_status"] = upload.processing_status
        
        # ProcessingTask-Daten
        tasks = ProcessingTask.query.filter_by(session_id=session_id).all()
        debug_info["db_data"]["processing_tasks"] = []
        for task in tasks:
            debug_info["db_data"]["processing_tasks"].append({
                "id": task.id,
                "status": task.status,
                "task_type": task.task_type,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "error_message": task.error_message
            })
        
        debug_info["status"]["processing_tasks_count"] = len(tasks)
        if tasks:
            latest_task = max(tasks, key=lambda t: t.created_at if t.created_at else datetime.min)
            debug_info["status"]["latest_task_status"] = latest_task.status
            debug_info["status"]["latest_task_id"] = latest_task.id
        
        # Redis-Daten für Session
        # Processing-Status
        processing_data = redis_client.hgetall(f"processing:{session_id}")
        if processing_data:
            formatted_processing = {}
            for k, v in processing_data.items():
                k = k.decode('utf-8') if isinstance(k, bytes) else k
                v = v.decode('utf-8') if isinstance(v, bytes) else v
                formatted_processing[k] = v
            debug_info["redis_data"]["processing"] = formatted_processing
            debug_info["status"]["redis_processing_status"] = formatted_processing.get("status", "unknown")
        else:
            debug_info["status"]["redis_processing_status"] = "not_found"
        
        # Results
        results_data = redis_client.hgetall(f"results:{session_id}")
        if results_data:
            formatted_results = {}
            for k, v in results_data.items():
                k = k.decode('utf-8') if isinstance(k, bytes) else k
                v = v.decode('utf-8') if isinstance(v, bytes) else v
                formatted_results[k] = v
            debug_info["redis_data"]["results"] = formatted_results
            debug_info["status"]["redis_results_available"] = True
        else:
            debug_info["status"]["redis_results_available"] = False
        
        # Datenbank-Zählungen
        debug_info["counts"]["flashcards"] = Flashcard.query.filter_by(upload_id=upload.id).count()
        debug_info["counts"]["questions"] = Question.query.filter_by(upload_id=upload.id).count()
        debug_info["counts"]["topics"] = Topic.query.filter_by(upload_id=upload.id).count()
        
        # Main-Topic
        main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
        if main_topic:
            debug_info["status"]["main_topic_exists"] = True
            debug_info["status"]["main_topic_name"] = main_topic.name
        else:
            debug_info["status"]["main_topic_exists"] = False
        
        # Status-Zusammenfassung für bessere Übersicht
        combined_status = "unknown"
        if debug_info["status"]["upload_processing_status"] == "completed":
            combined_status = "completed"
        elif debug_info["status"]["upload_processing_status"] == "processing":
            combined_status = "processing"
        elif debug_info["status"]["upload_processing_status"] == "error":
            combined_status = "error"
        
        debug_info["status"]["combined_status"] = combined_status
        
        # Log ausführliche Informationen
        logger.info(f"Debug-Info für Session {session_id}: {json.dumps(debug_info['status'])}")
        logger.info(f"Counts für Session {session_id}: {json.dumps(debug_info['counts'])}")
        
        return jsonify(debug_info), 200
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Debug-Informationen für {session_id}: {str(e)}", exc_info=True)
        return jsonify({
            "error": f"Fehler beim Abrufen der Debug-Informationen: {str(e)}",
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        }), 500 