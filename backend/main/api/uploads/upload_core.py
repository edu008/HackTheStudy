# api/upload_core.py
"""
Kernfunktionalität für Datei-Uploads.
Enthält die Haupt-Routen und Funktionen für Standard-Datei-Uploads.
"""

from flask import request, jsonify, Blueprint, current_app, g
from . import api_bp
from core.models import db, Upload, Question, Topic, Connection, Flashcard, User
from .auth import token_required
from .utils import allowed_file, extract_text_from_file, check_and_manage_user_sessions
from .token_tracking import check_credits_available, calculate_token_cost, deduct_credits
import uuid
import logging

# Konfiguriere Logger
logger = logging.getLogger(__name__)

# Konfiguriere maximale Dateigröße und Timeout
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
UPLOAD_TIMEOUT = 180  # 3 Minuten
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB pro Chunk - wird in upload_chunked.py verwendet

# Fehlercodes
ERROR_INVALID_INPUT = "INVALID_INPUT"
ERROR_PROCESSING_FAILED = "PROCESSING_FAILED"
ERROR_INSUFFICIENT_CREDITS = "INSUFFICIENT_CREDITS"

def create_error_response(message, error_code, details=None):
    """Erstellt eine standardisierte Fehlerantwort"""
    error_response = {
        "success": False,
        "message": message,
        "error": {
            "code": error_code
        }
    }
    
    if details:
        error_response["error"]["details"] = details
    
    return jsonify(error_response), 400

# Hilfsroute, die auf die richtige Upload-Route weiterleitet
@api_bp.route('/upload', methods=['GET', 'POST', 'OPTIONS'])
def upload_redirect():
    """
    Hilfsfunktion zur Weiterleitung auf den korrekten Upload-Endpunkt
    """
    if request.method == 'OPTIONS':
        return jsonify(success=True)
    
    # Bei POST auf /upload zur korrekten Datei-Upload-Route weiterleiten
    if request.method == 'POST':
        return upload_file()
    
    # Bei GET eine Hilfsnachricht zurückgeben
    return jsonify({
        "message": "Dies ist der Upload-Endpunkt. Für Datei-Uploads bitte POST-Anfragen an /api/v1/upload/file senden."
    })

@api_bp.route('/upload/file', methods=['POST', 'OPTIONS'])
@token_required
def upload_file():
    """
    Verarbeitet Datei-Uploads mit verbesserter Fehlerbehandlung und Timeout-Management.
    """
    try:
        # OPTIONS-Anfragen sofort beantworten
        if request.method == 'OPTIONS':
            response = jsonify({"success": True})
            return response
            
        # Überprüfe die Dateigröße
        if request.content_length and request.content_length > MAX_CONTENT_LENGTH:
            # Für große Dateien: Empfehle Chunk-Upload
            return jsonify({
                "success": False,
                "message": "Datei ist zu groß für direkten Upload",
                "error": {
                    "code": "FILE_TOO_LARGE",
                    "message": "Bitte verwenden Sie den Chunk-Upload für Dateien über 50MB",
                    "max_size": MAX_CONTENT_LENGTH,
                    "chunk_size": CHUNK_SIZE
                }
            }), 413
        
        # Setze einen längeren Timeout für die Verarbeitung
        request.timeout = UPLOAD_TIMEOUT
        
        if 'file' not in request.files:
            return create_error_response(
                "Keine Datei gefunden", 
                ERROR_INVALID_INPUT, 
                {"detail": "No file part"}
            )
        
        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename):
            return create_error_response(
                "Ungültige oder keine Datei ausgewählt", 
                ERROR_INVALID_INPUT, 
                {"detail": "Invalid or no file selected"}
            )
        
        # Verwende die übergebene session_id, falls vorhanden, sonst generiere eine neue
        session_id = request.form.get('session_id')
        user_id = getattr(request, 'user_id', None)
        
        # Log: Datei-Upload-Anfrage empfangen
        logger.info(f"Datei-Upload-Anfrage empfangen: {file.filename} (User-ID: {user_id})")
        
        # Überprüfe und verwalte Benutzer-Sessions
        # Diese Funktion wurde in session_management.py verschoben
        from .session_management import manage_user_sessions
        manage_user_sessions(user_id)
        
        # Lade den Dateiinhalt und extrahiere Text
        # Implementierung von extract_text_from_file bleibt in utils.py
        try:
            text_content, file_type, file_size, page_count = extract_text_from_file(file)
            
            if not text_content:
                return create_error_response(
                    "Textextraktion fehlgeschlagen", 
                    ERROR_PROCESSING_FAILED, 
                    {"detail": "Failed to extract text from file"}
                )
                
            # Generiere neue Session-ID, falls keine übergeben wurde
            if not session_id:
                session_id = str(uuid.uuid4())
                
            # Erstelle einen neuen Upload-Eintrag in der Datenbank
            new_upload = Upload(
                session_id=session_id,
                filename=file.filename,
                content=text_content,
                file_type=file_type,
                file_size=file_size,
                page_count=page_count,
                user_id=user_id if user_id else None
            )
            
            db.session.add(new_upload)
            db.session.commit()
            
            # Leite zur Verarbeitung weiter
            # Dies wurde in processing.py verschoben
            from .processing import initiate_processing
            return initiate_processing(session_id, new_upload.id)
            
        except Exception as e:
            logger.error(f"Fehler beim Verarbeiten der Datei: {str(e)}")
            return create_error_response(
                "Fehler bei der Verarbeitung", 
                ERROR_PROCESSING_FAILED, 
                {"detail": str(e)}
            )
            
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Upload: {str(e)}")
        return create_error_response(
            "Unerwarteter Fehler", 
            "UNEXPECTED_ERROR", 
            {"detail": str(e)}
        )

@api_bp.route('/results/<session_id>', methods=['GET'])
@token_required
def get_results(session_id):
    """
    Gibt die Verarbeitungsergebnisse für eine bestimmte Session zurück.
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
            
        # Aktualisiere den Zeitstempel der letzten Nutzung
        from .session_management import update_session_timestamp
        update_session_timestamp(session_id)
        
        # Hole alle Topics für den Upload
        topics = Topic.query.filter_by(upload_id=upload.id).all()
        topic_data = [topic.to_dict() for topic in topics]
        
        # Hole alle Verbindungen für den Upload
        connections = Connection.query.filter_by(upload_id=upload.id).all()
        connection_data = [connection.to_dict() for connection in connections]
        
        # Hole alle Fragen für den Upload
        questions = Question.query.filter_by(upload_id=upload.id).all()
        question_data = [question.to_dict() for question in questions]
        
        # Hole alle Flashcards für den Upload
        flashcards = Flashcard.query.filter_by(upload_id=upload.id).all()
        flashcard_data = [flashcard.to_dict() for flashcard in flashcards]
        
        # Erstelle das Ergebnis-Objekt
        result = {
            "success": True,
            "upload": {
                "id": upload.id,
                "session_id": upload.session_id,
                "filename": upload.filename,
                "file_type": upload.file_type,
                "file_size": upload.file_size,
                "page_count": upload.page_count,
                "created_at": upload.created_at.isoformat() if upload.created_at else None,
                "last_used_at": upload.last_used_at.isoformat() if upload.last_used_at else None
            },
            "topics": topic_data,
            "connections": connection_data,
            "questions": question_data,
            "flashcards": flashcard_data
        }
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Ergebnisse für Session {session_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": "Fehler beim Abrufen der Ergebnisse",
            "error": {"code": "RESULT_RETRIEVAL_ERROR", "detail": str(e)}
        }), 500 