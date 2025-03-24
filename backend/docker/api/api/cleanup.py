import logging
from core.models import db, Upload, Flashcard, Question, Topic, Connection, UserActivity
from core.redis_client import redis_client
import traceback
from api.log_utils import AppLogger

logger = logging.getLogger(__name__)

def cleanup_processing_for_session(session_id, error_reason="unknown"):
    """
    Bereinigt alle Ressourcen für eine bestimmte Session.
    
    Args:
        session_id (str): Die ID der Session
        error_reason (str): Der Grund für die Bereinigung
        
    Returns:
        bool: True bei erfolgreicher Bereinigung, False bei Fehler
    """
    try:
        # Finde die Upload-Session
        upload = Upload.query.filter_by(session_id=session_id).first()
        if not upload:
            logger.warning(f"Keine Upload-Session gefunden für Session ID: {session_id}")
            return False
            
        # Protokolliere den Bereinigungsprozess
        AppLogger.structured_log(
            "INFO",
            f"Starte Bereinigung für Session {session_id}",
            session_id=session_id,
            error_reason=error_reason,
            component="cleanup"
        )
        
        # Lösche alle mit der Session verbundenen Daten
        # 1. Lösche alle Flashcards
        Flashcard.query.filter_by(upload_id=upload.id).delete()
        
        # 2. Lösche alle Fragen
        Question.query.filter_by(upload_id=upload.id).delete()
        
        # 3. Lösche alle Verbindungen
        Connection.query.filter_by(upload_id=upload.id).delete()
        
        # 4. Lösche alle Themen
        Topic.query.filter_by(upload_id=upload.id).delete()
        
        # 5. Lösche alle Benutzeraktivitäten für diese Session
        UserActivity.query.filter_by(session_id=session_id).delete()
        
        # 6. Lösche den Upload-Eintrag selbst
        db.session.delete(upload)
        
        # 7. Lösche den Session-Lock in Redis
        try:
            redis_client.delete(f"session_lock:{session_id}")
        except Exception as redis_error:
            logger.warning(f"Fehler beim Löschen des Redis-Locks: {str(redis_error)}")
        
        # Commit der Änderungen
        db.session.commit()
        
        AppLogger.structured_log(
            "INFO",
            f"Bereinigung für Session {session_id} erfolgreich abgeschlossen",
            session_id=session_id,
            component="cleanup"
        )
        
        return True
        
    except Exception as e:
        error_msg = f"Fehler bei der Bereinigung der Session {session_id}: {str(e)}"
        AppLogger.track_error(
            session_id,
            "cleanup_error",
            error_msg,
            trace=traceback.format_exc()
        )
        logger.error(error_msg)
        
        # Rollback bei Fehler
        if 'db' in locals():
            db.session.rollback()
            
        return False 