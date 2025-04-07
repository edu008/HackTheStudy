# api/diagnostics.py
"""
Diagnostik- und Debug-Funktionen für Upload-Sessions
"""

import logging
import os
import time
from datetime import datetime, timedelta

from flask import jsonify, request, current_app
from werkzeug.utils import secure_filename

from core.models import db, Upload, Flashcard, Question, Topic
from core.redis_client import get_redis_client

# Logger konfigurieren
logger = logging.getLogger(__name__)

# Entferne den zirkulären Import
# from . import api_bp


def get_diagnostics(session_id):
    """
    Diagnostische Informationen für eine Upload-Session abrufen.
    
    Args:
        session_id: Die Session-ID des Uploads
        
    Returns:
        JSON-Antwort mit diagnostischen Informationen
    """
    try:
        # Authentifizierungs-Check (nur für Administratoren)
        # Hinweis: Die Authentifizierung sollte über einen Decorator erfolgen
        
        # Upload aus der Datenbank abrufen
        upload = Upload.query.filter_by(session_id=session_id).first()
        
        # Wenn kein Upload existiert
        if not upload:
            logger.error(f"Keine Session mit ID {session_id} gefunden")
            return jsonify({
                "success": False,
                "error": {"code": "SESSION_NOT_FOUND", "message": "Session nicht gefunden"}
            }), 404
            
        # Redis-Client holen
        redis_client = get_redis_client()
        
        # Verschiedene Redis-Einträge für die Session abfragen
        redis_data = {
            "upload": redis_client.hgetall(f"upload:{session_id}"),
            "upload_meta": redis_client.hgetall(f"upload:meta:{session_id}"),
            "chunks": redis_client.hgetall(f"upload:chunks:{session_id}"),
            "processing": redis_client.hgetall(f"processing:{session_id}"),
            "results": redis_client.hgetall(f"results:{session_id}")
        }
        
        # Redis-Daten in JSON-Format umwandeln (Bytes -> String)
        formatted_redis = {}
        for key, data in redis_data.items():
            if not data:
                formatted_redis[key] = {}
                continue
                
            formatted_redis[key] = {}
            for k, v in data.items():
                if isinstance(k, bytes):
                    k = k.decode('utf-8')
                if isinstance(v, bytes):
                    v = v.decode('utf-8')
                formatted_redis[key][k] = v
                
        # Ergebnisse erstellen
        diagnostics = {
            "session_id": session_id,
            "database": {
                "upload": upload.to_dict() if upload else None
            },
            "redis": formatted_redis,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return jsonify({
            "success": True,
            "diagnostics": diagnostics
        })
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Diagnose für Session {session_id}: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {"code": "DIAGNOSTICS_ERROR", "message": f"Fehler bei der Diagnose: {str(e)}"}
        }), 500


def debug_session_status(session_id):
    """
    Debug-Informationen zum Status einer Session abrufen.
    
    Args:
        session_id: Die Session-ID des Uploads
        
    Returns:
        JSON-Antwort mit Debug-Informationen
    """
    try:
        # Authentifizierungs-Check (nur für Administratoren oder den Besitzer)
        # Hinweis: Die Authentifizierung sollte über einen Decorator erfolgen
        
        # Redis-Client holen
        redis_client = get_redis_client()
        
        # Alle Redis-Schlüssel für die Session finden
        keys = redis_client.keys(f"*{session_id}*")
        
        # Debug-Informationen sammeln
        debug_info = {
            "session_id": session_id,
            "redis_keys": [k.decode('utf-8') if isinstance(k, bytes) else k for k in keys],
            "database": {}
        }
        
        # Datenbank-Informationen hinzufügen
        upload = Upload.query.filter_by(session_id=session_id).first()
        if upload:
            debug_info["database"]["upload"] = {
                "id": upload.id,
                "session_id": upload.session_id,
                "filename": upload.file_name_1,
                "status": upload.processing_status,
                "created_at": upload.created_at.isoformat() if upload.created_at else None,
                "updated_at": upload.updated_at.isoformat() if upload.updated_at else None
            }
            
        # Redis-Einträge abrufen und hinzufügen
        debug_info["redis_data"] = {}
        for key in keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            data = None
            
            # Je nach Schlüsseltyp unterschiedlich abrufen
            if ":{" in key_str:  # JSON-Daten
                data = redis_client.get(key)
                if data:
                    data = data.decode('utf-8') if isinstance(data, bytes) else data
            else:  # Hash-Daten
                data = redis_client.hgetall(key)
                if data:
                    formatted_data = {}
                    for k, v in data.items():
                        k = k.decode('utf-8') if isinstance(k, bytes) else k
                        v = v.decode('utf-8') if isinstance(v, bytes) else v
                        formatted_data[k] = v
                    data = formatted_data
                    
            debug_info["redis_data"][key_str] = data
            
        return jsonify({
            "success": True,
            "debug_info": debug_info
        })
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des Debug-Status für Session {session_id}: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": {"code": "DEBUG_ERROR", "message": f"Fehler beim Debug: {str(e)}"}
        }), 500


def get_session_info(session_id):
    """
    Gibt Informationen über den Status einer Session zurück.
    
    Args:
        session_id (str): Die ID der Session
        
    Returns:
        JSON Response mit dem Status der Session
    """
    try:
        logger.info(f"Verarbeite get_session_info für Session ID: {session_id}")
        
        # Erstelle eine Basis-Antwort
        result = {
            "success": True,
            "data": {
                "session_id": session_id,
                "status": "unknown",
                "processing_status": "unknown"
            }
        }
        
        # Zuerst Redis prüfen für schnellen Zugriff
        redis_client = get_redis_client()
        redis_status = redis_client.get(f"processing_status:{session_id}")
        redis_session_info = redis_client.hgetall(f"session_info:{session_id}")
        
        if redis_status:
            try:
                if isinstance(redis_status, bytes):
                    redis_status = redis_status.decode('utf-8')
                logger.info(f"Redis-Status für Session {session_id}: {redis_status}")
                result["data"]["processing_status"] = redis_status
                result["data"]["status"] = redis_status  # Für Abwärtskompatibilität
            except Exception as e:
                logger.warning(f"Fehler beim Decodieren des Redis-Status: {str(e)}")
                # Fallback für den Fall, dass redis_status nicht dekodiert werden kann
                result["data"]["processing_status"] = str(redis_status)
                result["data"]["status"] = str(redis_status)
                
        if redis_session_info:
            try:
                # Decode und konvertiere den Redis-Hash in ein Python-Dict
                session_info = {}
                for key, value in redis_session_info.items():
                    if isinstance(key, bytes):
                        key = key.decode('utf-8')
                    if isinstance(value, bytes):
                        value = value.decode('utf-8')
                    session_info[key] = value
                
                logger.info(f"Redis-Session-Info für {session_id}: {session_info}")
                
                # Extrahiere wichtige Informationen
                if "results_available" in session_info:
                    # Sicherstellen, dass der Wert ein Boolean ist
                    if isinstance(session_info["results_available"], str):
                        result["data"]["results_available"] = session_info["results_available"].lower() == "true"
                    else:
                        result["data"]["results_available"] = bool(session_info["results_available"])
                
                # Füge Zähler hinzu
                if "flashcards_count" in session_info:
                    try:
                        result["data"]["flashcards_count"] = int(session_info["flashcards_count"])
                    except (ValueError, TypeError):
                        result["data"]["flashcards_count"] = 0
                
                if "questions_count" in session_info:
                    try:
                        result["data"]["questions_count"] = int(session_info["questions_count"])
                    except (ValueError, TypeError):
                        result["data"]["questions_count"] = 0
                
                if "topics_count" in session_info:
                    try:
                        result["data"]["topics_count"] = int(session_info["topics_count"])
                    except (ValueError, TypeError):
                        result["data"]["topics_count"] = 0
                
                if "main_topic" in session_info:
                    result["data"]["main_topic"] = session_info["main_topic"]
            except Exception as e:
                logger.warning(f"Fehler beim Verarbeiten der Redis-Session-Info: {str(e)}")
        
        # Dann Datenbank prüfen für vollständige und persistente Informationen
        with current_app.app_context():
            upload = Upload.query.filter_by(session_id=session_id).first()
            
            if upload and hasattr(upload, 'id'):
                # Upload-Details hinzufügen
                result["data"]["status"] = upload.processing_status
                result["data"]["processing_status"] = upload.processing_status  # Dupliziert für Konsistenz
                
                if hasattr(upload, 'created_at') and upload.created_at:
                    result["data"]["created_at"] = upload.created_at.isoformat()
                
                if hasattr(upload, 'updated_at') and upload.updated_at:
                    result["data"]["updated_at"] = upload.updated_at.isoformat()
                
                if hasattr(upload, 'file_name_1'):
                    result["data"]["filename"] = upload.file_name_1
                
                # Dateiliste zusammenstellen
                files = []
                for i in range(1, 6):  # Maximal 5 Dateien
                    file_attr = f'file_name_{i}'
                    if hasattr(upload, file_attr) and getattr(upload, file_attr):
                        files.append(getattr(upload, file_attr))
                
                result["data"]["files"] = files
                
                # Zähle Flashcards, Fragen und Themen, um zu prüfen, ob Daten vorhanden sind
                flashcards_count = Flashcard.query.filter_by(upload_id=upload.id).count()
                questions_count = Question.query.filter_by(upload_id=upload.id).count()
                topics_count = Topic.query.filter_by(upload_id=upload.id).count()
                
                # Prüfe, ob es Themendaten gibt
                main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
                
                result["data"]["flashcards_count"] = flashcards_count
                result["data"]["questions_count"] = questions_count
                result["data"]["topics_count"] = topics_count
                
                # Ergebnisse sind verfügbar, wenn der Status "completed" ist oder wenn Daten gefunden wurden
                results_available = (
                    upload.processing_status == 'completed' or
                    flashcards_count > 0 or 
                    questions_count > 0 or 
                    topics_count > 0
                )
                result["data"]["results_available"] = results_available
                
                logger.info(f"Session {session_id}: Flashcards={flashcards_count}, Questions={questions_count}, Topics={topics_count}, Ergebnisse verfügbar={results_available}")
            else:
                logger.warning(f"Upload für Session {session_id} nicht in der Datenbank gefunden")
                
                # Wenn wir Redis-Daten haben, sind wir nicht zu besorgt
                if redis_status or redis_session_info:
                    logger.info(f"Session {session_id} nur in Redis gefunden - Cache-Informationen werden verwendet")
                else:
                    # Wenn wir auch keine Redis-Daten haben, ist das Session-Objekt vielleicht verloren gegangen
                    logger.error(f"Keine Upload-Daten für Session {session_id} gefunden (weder in Redis noch in DB)")
                    return jsonify({
                        "success": False,
                        "error": {
                            "code": "SESSION_NOT_FOUND",
                            "message": "Upload-Session nicht gefunden"
                        }
                    }), 404
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Session-Info: {str(e)}", exc_info=True)
        return jsonify({
            "success": False, 
            "error": {"code": "SESSION_INFO_ERROR", "message": f"Fehler beim Abrufen der Session-Info: {str(e)}"}
        }), 500


def get_session_status(session_id):
    """
    Gibt den Status einer Session zurück mit erweiterten Diagnoseinformationen.
    """
    try:
        redis_client = get_redis_client()
        
        # Datenbankabfragen in den Anwendungskontext einbetten
        with current_app.app_context():
            # Upload aus der Datenbank holen
            upload = Upload.query.filter_by(session_id=session_id).first()
            
            if not upload:
                return {
                    "success": False,
                    "error": {"code": "SESSION_NOT_FOUND", "message": "Session nicht gefunden"}
                }
            
            # Zähle Flashcards, Fragen und Themen, um zu prüfen, ob Daten vorhanden sind
            flashcards_count = Flashcard.query.filter_by(upload_id=upload.id).count()
            questions_count = Question.query.filter_by(upload_id=upload.id).count()
            topics_count = Topic.query.filter_by(upload_id=upload.id).count()
            
            # Prüfe, ob es Themendaten gibt
            main_topic = Topic.query.filter_by(upload_id=upload.id, is_main_topic=True).first()
            
        # Redis-Status abrufen
        redis_status = redis_client.get(f"processing_status:{session_id}")
        if redis_status:
            if isinstance(redis_status, bytes):
                redis_status = redis_status.decode('utf-8')
            else:
                redis_status = str(redis_status)
        
        # Ergebnisse verfügbar?
        results_available = (flashcards_count > 0 or questions_count > 0) and topics_count > 0 and main_topic is not None
        
        # Logging für Diagnose
        current_app.logger.info(f"Session {session_id} gefunden: Upload-ID={upload.id}, processing_status={upload.processing_status}")
        current_app.logger.info(f"Ergebnisse verfügbar für Session {session_id}: {results_available}")
        current_app.logger.info(f"Session {session_id} hat {flashcards_count} Flashcards und {questions_count} Questions")
        
        # Status zusammenfassen
        status_overview = {
            "db_status": upload.processing_status,
            "redis_status": redis_status,
            "results_available": results_available,
            "flashcards_count": flashcards_count,
            "questions_count": questions_count
        }
        
        current_app.logger.info(f"Statusübersicht für Session {session_id}: {status_overview}")
        
        data = {
            "session_id": session_id,
            "status": upload.processing_status,
            "processing_status": redis_status or upload.processing_status,
            "results_available": results_available,
            "flashcards_count": flashcards_count,
            "questions_count": questions_count
        }
        
        # Füge Dateinamen hinzu, falls vorhanden
        if hasattr(upload, 'file_name_1'):
            data["file_name"] = upload.file_name_1
        
        # Füge Zeitstempel hinzu, falls vorhanden
        if hasattr(upload, 'timestamp') and upload.timestamp:
            data["created_at"] = upload.timestamp.isoformat()
        elif hasattr(upload, 'created_at') and upload.created_at:
            data["created_at"] = upload.created_at.isoformat()
            
        if hasattr(upload, 'updated_at') and upload.updated_at:
            data["updated_at"] = upload.updated_at.isoformat()
        
        return {
            "success": True,
            "data": data
        }
            
    except Exception as e:
        current_app.logger.error(f"Fehler beim Abrufen des Session-Status: {str(e)}", exc_info=True)
        return {
            "success": False, 
            "error": {"code": "STATUS_ERROR", "message": f"Fehler beim Abrufen des Status: {str(e)}"}
        }
