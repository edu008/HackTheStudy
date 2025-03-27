# api/diagnostics.py
"""
Diagnostische Funktionen und Debug-Endpunkte für Uploads und Verarbeitung.
"""

from flask import jsonify, request
from . import api_bp
from .auth import token_required
import redis
import os
import logging
import time
import json
from core.models import Upload
from .processing import calculate_upload_progress, estimate_remaining_time

# Redis-Client direkt erstellen
redis_url = os.environ.get('REDIS_URL', 'redis://hackthestudy-backend-main:6379/0')
redis_client = redis.from_url(redis_url)

# Konfiguriere Logger
logger = logging.getLogger(__name__)

@api_bp.route('/diagnostics/<session_id>', methods=['GET'])
@token_required
def get_diagnostics(session_id):
    """
    Gibt diagnostische Informationen für eine Session zurück.
    """
    try:
        # Überprüfe, ob die Session existiert
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            return jsonify({
                "success": False,
                "message": "Session nicht gefunden",
                "error": {"code": "SESSION_NOT_FOUND"}
            }), 404
            
        # Hole alle verfügbaren Informationen aus Redis
        redis_keys = redis_client.keys(f"*:{session_id}")
        redis_data = {}
        
        for key in redis_keys:
            decoded_key = key.decode('utf-8')
            value = redis_client.get(key)
            
            # Versuche, den Wert zu dekodieren oder zu deserialisieren
            try:
                if value is not None:
                    decoded_value = value.decode('utf-8')
                    
                    # Versuche, JSON zu parsen
                    try:
                        parsed_value = json.loads(decoded_value)
                        redis_data[decoded_key] = parsed_value
                    except json.JSONDecodeError:
                        redis_data[decoded_key] = decoded_value
                else:
                    redis_data[decoded_key] = None
            except Exception as e:
                redis_data[decoded_key] = f"Konnte nicht dekodiert werden: {str(e)}"
                
        # Berechne den Fortschritt und die geschätzte verbleibende Zeit
        progress = calculate_upload_progress(session_id)
        remaining_time = estimate_remaining_time(session_id)
        
        # Hole die Task-ID, falls vorhanden
        task_id = redis_client.get(f"task_id:{session_id}")
        task_id = task_id.decode('utf-8') if task_id else None
        
        # Erstelle die Diagnose-Antwort
        diagnostics = {
            "success": True,
            "session_id": session_id,
            "upload": {
                "id": upload.id,
                "filename": upload.filename,
                "file_type": upload.file_type,
                "file_size": upload.file_size,
                "page_count": upload.page_count,
                "created_at": upload.created_at.isoformat() if upload.created_at else None,
                "last_used_at": upload.last_used_at.isoformat() if upload.last_used_at else None,
                "user_id": upload.user_id
            },
            "redis_data": redis_data,
            "processing": {
                "progress": progress,
                "remaining_time": remaining_time,
                "task_id": task_id
            }
        }
        
        return jsonify(diagnostics)
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Diagnose für Session {session_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": "Fehler beim Abrufen der Diagnose",
            "error": {"code": "DIAGNOSTIC_ERROR", "detail": str(e)}
        }), 500

@api_bp.route('/debug-status/<session_id>', methods=['GET'])
def debug_session_status(session_id):
    """
    Debug-Endpunkt für Entwickler, um schnell den Status einer Session zu überprüfen.
    Diese Route erfordert keine Authentifizierung, um Debugging zu erleichtern.
    """
    try:
        # Hole die wichtigsten Status-Informationen
        processing_status = redis_client.get(f"processing_status:{session_id}")
        processing_status = processing_status.decode('utf-8') if processing_status else "unbekannt"
        
        processing_progress = redis_client.get(f"processing_progress:{session_id}")
        processing_progress = float(processing_progress.decode('utf-8')) if processing_progress else 0
        
        last_update = redis_client.get(f"processing_last_update:{session_id}")
        last_update = int(last_update.decode('utf-8')) if last_update else None
        
        current_time = int(time.time())
        time_since_update = current_time - last_update if last_update else None
        
        task_id = redis_client.get(f"task_id:{session_id}")
        task_id = task_id.decode('utf-8') if task_id else None
        
        error_details = redis_client.get(f"error_details:{session_id}")
        error_details = error_details.decode('utf-8') if error_details else None
        
        # Hole Basis-Informationen aus der Datenbank
        upload = Upload.query.filter_by(session_id=session_id).first()
        upload_info = None
        
        if upload:
            upload_info = {
                "id": upload.id,
                "filename": upload.filename,
                "created_at": upload.created_at.isoformat() if upload.created_at else None,
                "user_id": upload.user_id
            }
            
        # Erstelle die Debug-Antwort
        debug_info = {
            "session_id": session_id,
            "status": processing_status,
            "progress": processing_progress,
            "task_id": task_id,
            "last_update": last_update,
            "time_since_update": time_since_update,
            "current_server_time": current_time,
            "upload": upload_info,
            "error": error_details
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des Debug-Status für Session {session_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": "Fehler beim Abrufen des Debug-Status",
            "error": {"detail": str(e)}
        }), 500

@api_bp.route('/session-info/<session_id>', methods=['GET', 'OPTIONS'])
def get_session_info(session_id):
    """
    Gibt Informationen zu einer Session zurück.
    Dies ist ein öffentlicher Endpunkt ohne Authentifizierungsanforderung.
    """
    # OPTIONS-Anfragen sofort beantworten
    if request.method == 'OPTIONS':
        return jsonify(success=True)
        
    try:
        # Verwende die Funktion aus session_management.py
        from .session_management import get_session_info as get_session_info_func
        session_info, error = get_session_info_func(session_id)
        
        if error:
            return jsonify({
                "success": False,
                "message": error,
                "error": {"code": "SESSION_INFO_ERROR"}
            }), 404
            
        # Erweitere die Informationen um Fortschritt und geschätzte verbleibende Zeit
        progress = calculate_upload_progress(session_id)
        remaining_time = estimate_remaining_time(session_id)
        
        session_info["progress"] = progress
        session_info["estimated_remaining_time"] = remaining_time
        
        # Hole Fehlerinformationen, falls vorhanden
        error_details = redis_client.get(f"error_details:{session_id}")
        if error_details:
            session_info["error"] = error_details.decode('utf-8')
            
        return jsonify({
            "success": True,
            "session_info": session_info
        })
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Session-Informationen für {session_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": "Fehler beim Abrufen der Session-Informationen",
            "error": {"code": "SESSION_INFO_ERROR", "detail": str(e)}
        }), 500 